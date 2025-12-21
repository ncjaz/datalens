#!/usr/bin/env python3
"""
DataLens Test Runner

This script runs tests against the fully loaded DataLens application.
All tests require the complete application to be initialized and running.

Usage:
    # Run all tests
    python run_tests.py

    # Run specific test file
    python run_tests.py test_preferences.py

    # Run specific test function
    python run_tests.py test_preferences.py::test_reset_button

    # Run with verbose output
    python run_tests.py -v

    # Run with coverage
    python run_tests.py --cov

Plugin Widget Testing:
    # Test a specific plugin's widgets
    python run_tests.py integration/plugins/test_plugin_widget_groups.py --plugin=capture

    # Test multiple plugins
    python run_tests.py integration/plugins/test_plugin_widget_groups.py --plugin=capture --plugin=widget_test

    # Test all available plugins
    python run_tests.py integration/plugins/test_plugin_widget_groups.py --test-all-plugins

    # Generate widget inventory report
    python run_tests.py integration/plugins/test_plugin_widget_groups.py --plugin=capture --generate-inventory

Environment:
    All tests run with the full DataLens application loaded. The app is
    initialized once before any tests run and shared across all test modules.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path so we can import datalens
tests_dir = Path(__file__).parent
project_root = tests_dir.parent
sys.path.insert(0, str(project_root / "src"))


def main() -> int:
    """Run pytest with appropriate configuration for full-app testing."""
    parser = argparse.ArgumentParser(
        description="Run DataLens tests against the fully loaded application",
        epilog="All tests require the complete DataLens application to be loaded.",
    )
    parser.add_argument(
        "test_path",
        nargs="?",
        help="Specific test file or test function to run (e.g., test_preferences.py or test_preferences.py::test_reset_button)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--cov",
        action="store_true",
        help="Run with coverage reporting",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        help="Run tests matching the given keyword expression",
    )
    parser.add_argument(
        "-x",
        "--exitfirst",
        action="store_true",
        help="Exit on first test failure",
    )
    parser.add_argument(
        "--lf",
        "--last-failed",
        action="store_true",
        dest="last_failed",
        help="Rerun only tests that failed last time",
    )
    parser.add_argument(
        "--keep-app-open",
        action="store_true",
        help="Keep the DataLens application window open after tests complete (for manual inspection)",
    )

    # Plugin testing options
    parser.add_argument(
        "--plugin",
        action="append",
        help="Plugin ID to test (can be specified multiple times). Example: --plugin=capture",
    )
    parser.add_argument(
        "--test-all-plugins",
        action="store_true",
        help="Test all available plugins",
    )
    parser.add_argument(
        "--generate-inventory",
        action="store_true",
        help="Generate detailed widget inventory report",
    )

    args, unknown_args = parser.parse_known_args()

    # Build pytest arguments
    pytest_args = [str(tests_dir)]

    if args.test_path:
        # If user specified a test path, use it instead of the directory
        pytest_args = [str(tests_dir / args.test_path)]

    # Always show verbose output by default so users know what tests ran
    if args.verbose:
        pytest_args.append("-vv")  # Extra verbose
    else:
        pytest_args.append("-v")  # Standard verbose (show test names)

    if args.cov:
        pytest_args.extend([
            "--cov=datalens",
            "--cov-report=html",
            "--cov-report=term",
        ])

    if args.keyword:
        pytest_args.extend(["-k", args.keyword])

    if args.exitfirst:
        pytest_args.append("-x")

    if args.last_failed:
        pytest_args.append("--lf")

    # Plugin testing options
    if args.plugin:
        for plugin_id in args.plugin:
            pytest_args.extend(["--plugin", plugin_id])

    if args.test_all_plugins:
        pytest_args.append("--test-all-plugins")

    if args.generate_inventory:
        pytest_args.append("--generate-inventory")

    # Add any unknown args (for pytest plugins, custom options, etc.)
    if unknown_args:
        pytest_args.extend(unknown_args)

    # Always show local variables on failure for better debugging
    pytest_args.append("--showlocals")

    # Pass keep-app-open flag to pytest via environment variable
    if args.keep_app_open:
        import os
        os.environ["DATALENS_TEST_KEEP_APP_OPEN"] = "1"

    # Import pytest here so we don't require it if just showing help
    try:
        import pytest
    except ImportError:
        print("ERROR: pytest is not installed. Install it with: pip install pytest pytest-qt", file=sys.stderr)
        return 1

    print("=" * 70)
    print("DataLens Test Runner")
    print("=" * 70)
    print("Running tests against fully loaded DataLens application")
    print(f"Test path: {pytest_args[0]}")
    if args.keep_app_open:
        print("Mode: Keep app open after tests (manual inspection)")
    print("=" * 70)
    print()

    # Run pytest with our configuration
    return pytest.main(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
