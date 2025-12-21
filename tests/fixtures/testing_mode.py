"""
Testing mode infrastructure for DataLens.

This module provides utilities for running tests in isolated environments:
- Isolated settings (copy of user settings or fresh defaults)
- Test projects (created through UI, automatically cleaned up)
- Automatic cleanup on test completion

Usage:
    with TestingEnvironment() as env:
        # env.settings_path points to isolated settings.json
        # env.test_project_root is available for test projects
        app = DataLensApp(testing_mode=env)
        # Run tests...
    # Cleanup happens automatically
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass(frozen=True)
class TestingEnvironmentConfig:
    """
    Configuration for test environment isolation.

    Attributes:
        copy_user_settings: If True, copy user's settings.json to test environment.
                          If False, start with fresh/default settings.
        keep_test_data: If True, preserve test data after tests complete.
                       If False (default), clean up test data automatically.
        test_project_name: Name of the test project to create (default: "test_project").
    """
    copy_user_settings: bool = False
    keep_test_data: bool = False
    test_project_name: str = "test_project"


@dataclass
class TestingEnvironment:
    """
    Isolated testing environment for DataLens.

    This class manages:
    - Temporary directory for all test data
    - Isolated settings.json (copy or fresh)
    - Test project directory
    - Automatic cleanup on exit

    Attributes:
        temp_root: Root directory for all test data
        settings_path: Path to isolated settings.json
        test_project_root: Path where test project will be created
        config: Configuration for this environment
    """
    temp_root: Path
    settings_path: Path
    test_project_root: Path
    config: TestingEnvironmentConfig

    @classmethod
    def create(cls, config: TestingEnvironmentConfig | None = None) -> TestingEnvironment:
        """
        Create a new isolated testing environment.

        Args:
            config: Configuration for the test environment. If None, uses defaults.

        Returns:
            Configured TestingEnvironment instance.
        """
        if config is None:
            config = TestingEnvironmentConfig()

        # Create temporary directory for all test data
        temp_root = Path(tempfile.mkdtemp(prefix="datalens_test_"))

        # Set up isolated settings directory
        settings_dir = temp_root / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_path = settings_dir / "settings.json"

        if config.copy_user_settings:
            # Copy user's actual settings
            try:
                from datalens.infra.paths import settings_json_path
                user_settings = settings_json_path()
                if user_settings.exists():
                    shutil.copy2(user_settings, settings_path)
            except Exception:
                # If copy fails, we'll start with fresh settings
                pass

        # If we didn't copy settings (or copy failed), create minimal defaults
        if not settings_path.exists():
            default_settings = {
                "enabled_plugins": [],
                "recent_projects": [],
                "theme_opacity": 1.0,
                "plugin_overrides": {},
                "keyboard_shortcuts": {},
                "plugin_preferences": {},
            }
            settings_path.write_text(json.dumps(default_settings, indent=2))

        # Set up test project directory
        projects_dir = temp_root / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        test_project_root = projects_dir / config.test_project_name

        # If test project already exists, delete it first (ensures clean state)
        if test_project_root.exists():
            try:
                shutil.rmtree(test_project_root)
            except Exception:
                pass

        return cls(
            temp_root=temp_root,
            settings_path=settings_path,
            test_project_root=test_project_root,
            config=config,
        )

    def cleanup(self) -> None:
        """
        Clean up the testing environment.

        Removes all temporary data unless keep_test_data is True.
        """
        if self.config.keep_test_data:
            print(f"Test data preserved at: {self.temp_root}")
            return

        try:
            shutil.rmtree(self.temp_root)
        except Exception as exc:
            # Best-effort cleanup
            print(f"Warning: Failed to clean up test environment: {exc}")

    def prepare_test_project(self) -> Path:
        """
        Prepare the test project directory.

        This creates the directory if it doesn't exist and returns the path.
        Tests should use the UI to actually create/populate the project.

        Returns:
            Path to test project root directory.
        """
        self.test_project_root.mkdir(parents=True, exist_ok=True)
        return self.test_project_root

    def get_settings_override_env(self) -> dict[str, str]:
        """
        Get environment variables to override settings paths.

        Returns:
            Dictionary of environment variables to set for isolated testing.
        """
        return {
            "DATALENS_USER_DATA_DIR": str(self.temp_root / "settings"),
            "DATALENS_SETTINGS_PATH": str(self.settings_path),
        }


@contextmanager
def isolated_test_environment(
    config: TestingEnvironmentConfig | None = None,
) -> Generator[TestingEnvironment, None, None]:
    """
    Context manager for isolated test environment.

    This is the recommended way to use testing mode:

    Example:
        with isolated_test_environment() as env:
            # Set up environment variables
            import os
            os.environ.update(env.get_settings_override_env())

            # Launch app in testing mode
            app = DataLensApp()
            # ... run tests ...

        # Cleanup happens automatically here

    Args:
        config: Configuration for the test environment.

    Yields:
        TestingEnvironment instance with isolated settings and project paths.
    """
    env = TestingEnvironment.create(config)
    try:
        yield env
    finally:
        env.cleanup()


def get_test_project_root(env: TestingEnvironment) -> Path:
    """
    Get the test project root path.

    This is a helper that tests can use to get the project path.

    Args:
        env: The testing environment.

    Returns:
        Path where test project should be created.
    """
    return env.test_project_root


def delete_test_project_if_exists(env: TestingEnvironment) -> None:
    """
    Delete the test project if it exists.

    This is useful for ensuring clean state before tests run.

    Args:
        env: The testing environment.
    """
    if env.test_project_root.exists():
        try:
            shutil.rmtree(env.test_project_root)
        except Exception:
            pass


__all__ = [
    "TestingEnvironment",
    "TestingEnvironmentConfig",
    "isolated_test_environment",
    "get_test_project_root",
    "delete_test_project_if_exists",
]
