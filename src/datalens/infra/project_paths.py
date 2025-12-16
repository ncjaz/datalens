from __future__ import annotations

from pathlib import Path


def project_data_dir(project_root: Path) -> Path:
    """
    Return the project-local DataLens data directory.

    This is where project-scoped state lives (SQLite DB, caches, etc.) and should
    be kept separate from user media folders.
    """
    return Path(project_root) / ".datalens"


def project_db_path(project_root: Path) -> Path:
    """
    Return the default SQLite database path for a project.

    Layout:
        <project_root>/.datalens/project.sqlite
    """
    return project_data_dir(project_root) / "project.sqlite"


def project_meta_path(project_root: Path) -> Path:
    """
    Return the derived project metadata JSON path.

    Layout:
        <project_root>/.datalens/project_meta.json
    """
    return project_data_dir(project_root) / "project_meta.json"


def project_source_dir(project_root: Path) -> Path:
    """
    Return the default project "source" directory.

    This is the root directory that contains user media (images/videos) for the
    project. In V2 (matching V1's common usage), this is the project root itself
    so existing folder structures (subdirectories, nested datasets) work without
    forcing a specific `media/` layout.

    Future: we may make this configurable per project (e.g. project_root/media).
    """
    return Path(project_root)
