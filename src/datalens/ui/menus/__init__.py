"""
UI menus package.

Keep this package `__init__` lightweight: importing `datalens.ui.menus.*`
submodules should not accidentally pull in the full Qt menubar wiring (which
can create circular imports during autodoc and tool-time imports).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datalens.ui.menus.factory import create_menubar
    from datalens.ui.menus.menubar import DatalensMenuBar


def __getattr__(name: str):  # pragma: no cover
    if name == "DatalensMenuBar":
        from datalens.ui.menus.menubar import DatalensMenuBar as cls

        return cls
    if name == "create_menubar":
        from datalens.ui.menus.factory import create_menubar as fn

        return fn
    raise AttributeError(name)

__all__ = ["DatalensMenuBar", "create_menubar"]
