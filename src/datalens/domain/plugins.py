"""
Backward-compatible import shim.

V2 originally used `datalens.domain.plugins` for plugin-related domain types.
The module was later renamed to `datalens.domain.plugin` to better reflect that
it defines the contracts for a single plugin definition.

Keep this shim so internal code and Sphinx autosummary don't break.
"""

from datalens.domain.plugin import *  # noqa: F403

