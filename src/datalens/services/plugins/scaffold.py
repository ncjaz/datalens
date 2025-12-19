from __future__ import annotations

import json
import re
from string import Template
from dataclasses import dataclass
from pathlib import Path

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginKind, PluginStage


_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
log = get_logger(__name__)


class PluginScaffoldError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginScaffoldRequest:
    plugin_id: str
    name: str
    version: str
    stage: PluginStage
    kind: PluginKind
    description: str = ""
    author: str = ""
    nav_label: str | None = None


@dataclass(frozen=True)
class PluginScaffoldResult:
    plugin_root: Path
    manifest_path: Path
    plugin_py_path: Path


def validate_plugin_id(plugin_id: str) -> str:
    pid = str(plugin_id).strip()
    if not pid:
        raise PluginScaffoldError("Plugin ID is required.")
    if not _PLUGIN_ID_RE.match(pid):
        raise PluginScaffoldError(
            "Plugin ID must match: lowercase letters/numbers, underscores or dashes (2-64 chars)."
        )
    return pid


def _derive_nav_label(name: str) -> str:
    words = [w for w in re.split(r"\s+", str(name).strip()) if w]
    if not words:
        return "?"
    if len(words) >= 2:
        label = (words[0][:1] + words[1][:1]).upper()
    else:
        label = words[0][:1].upper()
    return label or "?"


def _normalize_nav_label(raw: str | None, *, name: str) -> str:
    value = (raw or "").strip().upper()
    if value:
        return value[:2]
    return _derive_nav_label(name)[:2]


def _manifest_payload(req: PluginScaffoldRequest) -> dict[str, object]:
    # We keep the initial manifest minimal. Features can be added later once
    # the plugin exposes actual runtime entrypoints beyond `plugin.py`.
    payload: dict[str, object] = {
        "id": req.plugin_id,
        "name": req.name,
        "version": req.version,
        "description": req.description or "",
        "nav_label": _normalize_nav_label(req.nav_label, name=req.name),
        "stage": req.stage.value,
        "author": req.author or None,
        "features": [
            {
                "id": req.kind.value,
                "kind": req.kind.value,
                "entrypoint": "plugin:get_plugin",
                "display_name": req.name,
                "description": req.description or "",
            }
        ],
    }
    # Remove nulls for readability.
    return {k: v for k, v in payload.items() if v is not None}


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "scaffold_templates"


def _render_template(filename: str, *, values: dict[str, str]) -> str:
    """
    Render a scaffold template file using `${...}` placeholders.

    We keep templates as files (not giant strings) so editing the scaffold output
    is as simple as editing a `.tmpl` file.
    """
    path = _templates_dir() / filename
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise PluginScaffoldError(f"Missing scaffold template: {path}") from exc
    return Template(raw).safe_substitute(values)


def _plugin_class_name_from_id(plugin_id: str) -> str:
    parts = [p for p in re.split(r"[_-]+", plugin_id) if p]
    base = "".join(p[:1].upper() + p[1:] for p in parts) or "Plugin"
    if base[:1].isdigit():
        base = f"Plugin{base}"
    return f"{base}Plugin"

def _plugin_py_template(req: PluginScaffoldRequest) -> str:
    class_name = _plugin_class_name_from_id(req.plugin_id)
    values = {
        "PLUGIN_ID": req.plugin_id,
        "PLUGIN_NAME": req.name,
        "PLUGIN_CLASS_NAME": class_name,
    }
    workspace_extras = ""
    if req.kind == PluginKind.WORKSPACE:
        workspace_extras = _render_template("plugin_workspace_extras.py.tmpl", values=values).rstrip() + "\n"
    values["WORKSPACE_EXTRAS"] = workspace_extras
    return _render_template("plugin_common.py.tmpl", values=values)


def scaffold_plugin(*, root_dir: Path, request: PluginScaffoldRequest) -> PluginScaffoldResult:
    """
    Create a new plugin folder with a minimal manifest + plugin.py.

    This is synchronous file IO; callers should run it off the UI thread (loader/IoWriter).
    """
    root_dir = Path(root_dir)
    plugin_id = validate_plugin_id(request.plugin_id)
    if not request.name.strip():
        raise PluginScaffoldError("Plugin name is required.")
    if not request.version.strip():
        raise PluginScaffoldError("Plugin version is required.")

    plugin_root = root_dir / plugin_id
    manifest_path = plugin_root / "manifest.json"
    plugin_py_path = plugin_root / "plugin.py"

    if plugin_root.exists():
        raise PluginScaffoldError(f"Plugin folder already exists: {plugin_root}")

    log.info(
        "Scaffolding plugin",
        extra={"operation": "plugin_scaffold", "phase": "start", "plugin_id": plugin_id, "plugin_root": str(plugin_root)},
    )
    plugin_root.mkdir(parents=True, exist_ok=False)

    # Make the plugin root a package to enable relative imports across files.
    (plugin_root / "__init__.py").write_text(
        _render_template(
            "package_init.py.tmpl",
            values={"PLUGIN_ID": plugin_id, "PLUGIN_NAME": request.name, "PLUGIN_CLASS_NAME": _plugin_class_name_from_id(plugin_id), "WORKSPACE_EXTRAS": ""},
        ),
        encoding="utf-8",
    )

    # Create subpackages only where we provide scaffolding that matches the plugin kind.
    if request.kind == PluginKind.WORKSPACE:
        ui_dir = plugin_root / "ui"
        ui_dir.mkdir(exist_ok=False)
        (ui_dir / "__init__.py").write_text(_render_template("ui_init.py.tmpl", values={"PLUGIN_ID": plugin_id, "PLUGIN_NAME": request.name, "PLUGIN_CLASS_NAME": ""}), encoding="utf-8")
        (ui_dir / "workspace.py").write_text(_render_template("ui_workspace.py.tmpl", values={"PLUGIN_ID": plugin_id, "PLUGIN_NAME": request.name, "PLUGIN_CLASS_NAME": ""}), encoding="utf-8")
    else:
        services_dir = plugin_root / "services"
        services_dir.mkdir(exist_ok=False)
        (services_dir / "__init__.py").write_text(_render_template("services_init.py.tmpl", values={"PLUGIN_ID": plugin_id, "PLUGIN_NAME": request.name, "PLUGIN_CLASS_NAME": ""}), encoding="utf-8")
        (services_dir / "service.py").write_text(_render_template("services_service.py.tmpl", values={"PLUGIN_ID": plugin_id, "PLUGIN_NAME": request.name, "PLUGIN_CLASS_NAME": ""}), encoding="utf-8")

    manifest_path.write_text(
        json.dumps(_manifest_payload(request), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    plugin_py_path.write_text(_plugin_py_template(request), encoding="utf-8")

    log.info(
        "Plugin scaffold created",
        extra={
            "operation": "plugin_scaffold",
            "phase": "end",
            "plugin_id": plugin_id,
            "plugin_root": str(plugin_root),
        },
    )
    return PluginScaffoldResult(
        plugin_root=plugin_root,
        manifest_path=manifest_path,
        plugin_py_path=plugin_py_path,
    )
