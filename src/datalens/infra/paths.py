from __future__ import annotations

import os
from pathlib import Path


def datalens_user_data_dir(*, app_name: str = "datalens") -> Path:
    """
    Return the per-user DataLens data directory.

    This is where logs and lightweight config (JSON) live.
    """
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(root) / app_name
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / app_name
    return Path.home() / ".local" / "share" / app_name


def settings_json_path() -> Path:
    """Default path for persisted AppSettings."""
    return datalens_user_data_dir() / "settings.json"


def user_plugins_dir() -> Path:
    """
    Return the per-user plugin directory.

    External plugins (written by users/third parties) can be dropped into this
    folder. Shipped plugins bundled with the app live in the package under
    `datalens/plugins/`.
    """
    return datalens_user_data_dir() / "plugins"
