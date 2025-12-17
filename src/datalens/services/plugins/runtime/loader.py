"""
Plugin runtime module loader.

This module is responsible for importing a plugin's `plugin.py` entrypoint
without requiring it to be installed as a Python package.
"""

from __future__ import annotations

import importlib
import sys
import types
from hashlib import sha1
from pathlib import Path

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.services.plugins.registry import PluginOrigin, PluginRecord
from datalens.services.plugins.runtime.contracts import BasePlugin, NoopPlugin
from datalens.services.plugins.runtime.types import PluginLoadError

log = get_logger(__name__)


def _safe_identifier(text: str) -> str:
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in text)


def _module_name_for_plugin(*, origin: PluginOrigin, plugin_id: PluginId, plugin_root: Path) -> str:
    digest = sha1(str(plugin_root).encode("utf-8")).hexdigest()[:10]
    return f"datalens._plugins.{origin.value}.{_safe_identifier(str(plugin_id))}_{digest}"


def _load_user_plugin_module(*, module_base: str, plugin_root: Path) -> types.ModuleType:
    """
    Load `plugin.py` from an arbitrary directory as a package-backed module.

    This enables relative imports within the plugin directory:
      from .ui.panel import ...
    """
    plugin_py = plugin_root / "plugin.py"
    if not plugin_py.exists():
        raise FileNotFoundError(f"Missing {plugin_py.name}")

    pkg_name = module_base
    mod_name = f"{pkg_name}.plugin"

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(plugin_root)]  # type: ignore[attr-defined]
    sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(mod_name, plugin_py)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to import module from {plugin_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def _load_shipped_plugin_module(plugin_root: Path) -> types.ModuleType:
    """
    Import shipped plugin runtime using its in-package module name.

    Shipped plugins live under `datalens/plugins/` and should be importable as
    `datalens.plugins.<...>.plugin`.
    """
    plugins_root = Path(__file__).resolve().parents[3] / "plugins"
    try:
        rel = plugin_root.resolve().relative_to(plugins_root.resolve())
    except Exception as exc:
        raise PluginLoadError(f"Plugin root {plugin_root} is not under {plugins_root}") from exc

    parts = ["datalens", "plugins", *[p for p in rel.parts if p]]
    module_path = ".".join(parts + ["plugin"])
    return importlib.import_module(module_path)


def _plugin_from_module(module: types.ModuleType) -> BasePlugin:
    candidate = getattr(module, "PLUGIN", None)
    if candidate is not None:
        return candidate  # type: ignore[return-value]

    factory = getattr(module, "get_plugin", None)
    if callable(factory):
        plugin = factory()
        return plugin

    raise PluginLoadError("plugin.py must export PLUGIN or get_plugin()")


def load_plugin_instance(record: PluginRecord) -> BasePlugin:
    plugin_root = record.location.root_dir
    plugin_id = record.definition.id

    plugin_py = plugin_root / "plugin.py"
    if not plugin_py.exists():
        return NoopPlugin(plugin_id)

    log.debug(
        "Loading plugin runtime",
        extra={"operation": "plugin_load", "phase": "start", "plugin_id": str(plugin_id)},
    )
    if record.location.origin == PluginOrigin.SHIPPED:
        module = _load_shipped_plugin_module(plugin_root)
    else:
        module_base = _module_name_for_plugin(
            origin=record.location.origin,
            plugin_id=plugin_id,
            plugin_root=plugin_root,
        )
        module = _load_user_plugin_module(module_base=module_base, plugin_root=plugin_root)

    plugin = _plugin_from_module(module)
    if getattr(plugin, "plugin_id", None) != plugin_id:
        raise PluginLoadError(
            f"plugin_id mismatch for {plugin_id}: runtime returned {getattr(plugin,'plugin_id',None)!r}"
        )

    log.debug(
        "Plugin runtime loaded",
        extra={"operation": "plugin_load", "phase": "end", "plugin_id": str(plugin_id)},
    )
    return plugin

