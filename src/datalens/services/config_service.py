from __future__ import annotations

from pathlib import Path

from datalens.core.app_settings import load_app_settings, save_app_settings
from datalens.domain.settings import AppSettings
from datalens.infra.paths import settings_json_path
from datalens.services.settings_store import SettingsStore, default_settings_store


def load_settings(path: Path | None = None) -> AppSettings:
    """Load persisted application settings."""
    return load_app_settings(path or settings_json_path())


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    """Persist application settings."""
    save_app_settings(path or settings_json_path(), settings)


def settings_store(path: Path | None = None) -> SettingsStore:
    """
    Return a `SettingsStore` for `settings.json`.

    Prefer using this (or `update_settings`) from UI and background systems so
    settings updates are atomic and consistent.
    """
    return SettingsStore(path) if path is not None else default_settings_store()


def update_settings(mutator, *, path: Path | None = None) -> AppSettings:
    """Atomic load -> mutate -> save convenience wrapper."""
    return settings_store(path).update(mutator)
