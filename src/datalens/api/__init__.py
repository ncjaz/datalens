"""
Public API surface for plugin and app developers.

This package intentionally avoids eager re-exports (``from .plugins import *``)
because they create circular imports during bootstrap (for example, Sphinx
autodoc importing `datalens.core.context`, which imports stable IDs from
`datalens.api.sharing`).

Use the explicit submodules instead:

- `datalens.api.plugins` – plugin contracts and helper types
- `datalens.api.sharing` – canonical capability/command IDs
"""

from __future__ import annotations

# Do not import submodules here: keep this package import side-effect free to
# avoid circular imports during bootstrap and documentation builds.
__all__ = ["plugins", "sharing"]
