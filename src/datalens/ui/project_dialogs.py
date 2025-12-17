from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def choose_existing_project_root(
    *,
    parent: QWidget,
    start_dir: Path | None = None,
    typed_path: Path | None = None,
) -> Path | None:
    """
    Choose an existing project root folder.

    If `typed_path` is a valid existing directory, it is returned without
    showing a dialog. Otherwise, a directory picker is shown.
    """
    if typed_path is not None and typed_path.exists() and typed_path.is_dir():
        return typed_path

    directory = QFileDialog.getExistingDirectory(
        parent,
        "Open project folder",
        str(start_dir) if start_dir is not None else "",
    )
    if not directory:
        return None
    return Path(directory)


def choose_new_project_root(
    *,
    parent: QWidget,
    start_dir: Path | None = None,
    typed_path: Path | None = None,
) -> Path | None:
    """
    Choose (and create if needed) a project root folder.

    If `typed_path` is provided, it is created (if missing) and returned.
    Otherwise, a folder picker is shown (user may create folders via the dialog).
    """
    if typed_path is not None:
        try:
            if typed_path.exists():
                if not typed_path.is_dir():
                    QMessageBox.warning(
                        parent,
                        "New Project",
                        f"Path exists but is not a folder:\n{typed_path}",
                    )
                    return None
            else:
                typed_path.mkdir(parents=True, exist_ok=False)
            return typed_path
        except Exception as exc:
            QMessageBox.critical(parent, "New Project", f"Failed to create project folder:\n{exc}")
            return None

    directory = QFileDialog.getExistingDirectory(
        parent,
        "Create new project folder",
        str(start_dir) if start_dir is not None else "",
    )
    if not directory:
        return None
    return Path(directory)

