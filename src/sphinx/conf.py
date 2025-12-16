"""Sphinx configuration for the DataLens V2 documentation."""
from __future__ import annotations

import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import sphinx.ext.autodoc.typehints as sphinx_typehints

V2_SRC_ROOT = Path(__file__).resolve().parents[1]
SPHINX_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(SPHINX_ROOT))
sys.path.insert(0, str(V2_SRC_ROOT))


def _make_qt_stub_module(name: str, class_names: list[str]) -> types.ModuleType:
    module = types.ModuleType(name)

    def _factory(attr: str):
        return type(attr, (), {"__init__": lambda self, *args, **kwargs: None})

    for class_name in class_names:
        setattr(module, class_name, _factory(class_name))

    def __getattr__(attr: str):  # type: ignore[override]
        dummy = _factory(attr)
        setattr(module, attr, dummy)
        return dummy

    module.__getattr__ = __getattr__  # type: ignore[assignment]
    return module


# Lightweight Qt stubs so autodoc can import UI modules without native Qt libs.
qtcore = _make_qt_stub_module("PySide6.QtCore", ["QObject", "QEvent", "QSize"])


class _QtEnum:
    def __init__(self, value: int = 0):
        self.value = value

    def __int__(self):
        return self.value

    def __or__(self, other):
        other_value = getattr(other, "value", int(other)) if other is not None else 0
        return _QtEnum(int(self) | int(other_value))

    def __and__(self, other):
        other_value = getattr(other, "value", int(other)) if other is not None else 0
        return _QtEnum(int(self) & int(other_value))


qtcore.Qt = type("Qt", (), {"__getattr__": lambda self, name: _QtEnum(0)})()

qtgui = _make_qt_stub_module("PySide6.QtGui", ["QColor", "QIcon", "QPainter", "QPixmap"])
qtwidgets = _make_qt_stub_module(
    "PySide6.QtWidgets", ["QApplication", "QWidget", "QMainWindow", "QDialog"]
)
qtnetwork = _make_qt_stub_module("PySide6.QtNetwork", ["QLocalServer", "QLocalSocket"])

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
pyside6.QtGui = qtgui
pyside6.QtWidgets = qtwidgets
pyside6.QtNetwork = qtnetwork
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtCore"] = qtcore
sys.modules["PySide6.QtGui"] = qtgui
sys.modules["PySide6.QtWidgets"] = qtwidgets
sys.modules["PySide6.QtNetwork"] = qtnetwork

shiboken6 = types.ModuleType("shiboken6")
shiboken6.isValid = lambda obj=None: True
sys.modules["shiboken6"] = shiboken6

# Mock optional heavy dependencies (kept small; add as V2 grows).
for module_name in ["numpy", "cv2", "torch", "PIL", "OpenGL", "OpenGL.GL"]:
    sys.modules.setdefault(module_name, MagicMock())

project = "DataLens V2"
author = "rsCapture contributors"
copyright = f"{datetime.now():%Y}, {author}"

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "autosummary_shortener",
]

autosummary_generate = True
autosummary_imported_members = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
]

# Treat fenced blocks like ```mermaid as the ``mermaid`` directive so existing
# Markdown (including the architecture audit) renders diagrams.
myst_fence_as_directive = ["mermaid"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

root_doc = "sphinx/index"

templates_path = ["_templates"]
exclude_patterns: list[str] = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    # Keep Sphinx from trying to parse autosummary templates as documentation pages.
    "_templates/**",
    "_static/**",
    "sphinx/_templates/**",
    "sphinx/_static/**",
    "sphinx/_build/**",
]

html_theme = os.environ.get("SPHINX_THEME", "furo")
html_static_path = ["_static"]
if html_theme == "pydata_sphinx_theme":
    html_theme_options = {
        "navbar_start": ["navbar-logo"],
        "navbar_center": ["navbar-nav"],
        "navbar_end": ["search-button", "theme-switcher", "navbar-icon-links"],
        "show_prev_next": False,
        "show_nav_level": 2,
        "secondary_sidebar_items": ["page-toc"],
    }
    html_context = {"default_mode": "dark"}
elif html_theme == "furo":
    html_theme_options = {"navigation_with_keys": True}
    html_context = {}
else:
    html_theme_options = {}
    html_context = {}

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_inherit_docstrings = True
autodoc_typehints = "none"
sphinx_typehints.record_typehints = lambda *args, **kwargs: None

# Match the feel of the Qt docs: show the full import path on the module page,
# but keep object headings compact (e.g. "class LoaderContext" instead of
# "class datalens.infra.background.loader_context.LoaderContext").
add_module_names = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "qt": ("https://doc.qt.io/qtforpython/", None),
}

nitpicky = False


def setup(app):
    """Lightweight Sphinx hooks."""

    def _suppress_typehints(app, what, name, obj, options, signature, return_annotation):
        return signature, None

    def _skip_members_without_module(app, what, name, obj, skip, options):
        # Some stub objects (or instance-valued attributes) can trip autodoc's
        # introspection logic; skip them to keep API builds stable.
        if not hasattr(obj, "__module__"):
            return True
        return skip

    def _filter_members_for_large_classes(app, what, name, obj, skip, options):
        if what != "class":
            return skip
        member_count = len([m for m in dir(obj) if not m.startswith("_")])
        if member_count > 20:
            options["members"] = False
        return skip

    app.connect("autodoc-process-signature", _suppress_typehints)
    app.connect("autodoc-skip-member", _skip_members_without_module)
    app.connect("autodoc-skip-member", _filter_members_for_large_classes)
