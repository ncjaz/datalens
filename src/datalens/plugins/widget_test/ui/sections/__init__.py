"""
Widget Test workspace sections.

The widget test plugin is a developer harness: it aggregates small UI panels that
exercise core systems (widgets, loader runner, shortcuts, gesture routing, etc.).

To avoid a single monolithic `workspace.py`, each panel lives in its own module.
"""

from .buttons import build_buttons_section
from .checkboxes import build_checkboxes_section
from .icons import build_icons_section
from .loader_tests import build_loader_test_section
from .project_close_policy import build_project_close_policy_section
from .sharing import build_sharing_section
from .shortcuts_advanced import build_shortcuts_advanced_section
from .shortcuts_basic import build_shortcuts_section
from .toggles import build_toggles_section

__all__ = [
    "build_buttons_section",
    "build_checkboxes_section",
    "build_icons_section",
    "build_loader_test_section",
    "build_project_close_policy_section",
    "build_sharing_section",
    "build_shortcuts_advanced_section",
    "build_shortcuts_section",
    "build_toggles_section",
]
