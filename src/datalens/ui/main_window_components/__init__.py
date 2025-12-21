"""
MainWindow components.

These helpers exist to prevent `datalens.ui.main_window` from becoming a monolith.
MainWindow remains the public entrypoint, but implementation details live here.
"""

from .app_context import try_get_app_context
from .project_actions import ProjectActionsController
from .status_bar import StatusBarController
from .ui_state import MainWindowUiStateController
from .workspaces import WorkspacesController

__all__ = [
    "MainWindowUiStateController",
    "ProjectActionsController",
    "StatusBarController",
    "WorkspacesController",
    "try_get_app_context",
]
