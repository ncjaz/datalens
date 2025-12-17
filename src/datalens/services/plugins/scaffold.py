from __future__ import annotations

import json
import re
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

def _plugin_class_name_from_id(plugin_id: str) -> str:
    parts = [p for p in re.split(r"[_-]+", plugin_id) if p]
    base = "".join(p[:1].upper() + p[1:] for p in parts) or "Plugin"
    if base[:1].isdigit():
        base = f"Plugin{base}"
    return f"{base}Plugin"

def _focus_hooks_template(*, include: bool) -> str:
    if not include:
        return ""
    return """
    def on_focus(self, ctx: PluginAppContext) -> None:
        \"\"\"Called when this workspace becomes active in the UI.\"\"\"
        return None

    def on_defocus(self, ctx: PluginAppContext) -> None:
        \"\"\"Called when this workspace is no longer active in the UI.\"\"\"
        return None
"""


def _plugin_py_template(req: PluginScaffoldRequest) -> str:
    class_name = _plugin_class_name_from_id(req.plugin_id)
    return f"""from __future__ import annotations

from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.services.plugins.runtime import BasePlugin, PluginAppContext, PluginProjectContext, PluginFutureResult


log = get_logger(__name__)


class {class_name}(BasePlugin):
    \"\"\"Plugin runtime entrypoint for `{req.name}`.

    Notes for plugin authors:
    - All hooks run on the caller thread (typically a background loader stage).
      Keep hooks fast; schedule heavy work to background systems (DB/IoWriter/threadpool).
    - Do not touch Qt widgets from background threads. Only mutate UI on the Qt thread.
    - Project hooks may be called with no UI focus (headless service behavior).

    Hook order (typical):
    - `on_load` once per app run when enabled
    - (optional) `on_project_migrate` then `on_project_opened` when a project is opened
    - `on_project_closing` on close/switch (return Futures for flush waits)
    - `on_unload` when disabled or app exits

    Workspace plugins (kind=`workspace`) may also receive:
    - `on_defocus` then `on_focus` when switching active workspaces
    \"\"\"

    @property
    def plugin_id(self) -> PluginId:
        return PluginId({req.plugin_id!r})

    def on_load(self, ctx: PluginAppContext) -> None:
        \"\"\"App-scope setup.

        Do lightweight registration only (menus, actions, capability providers).
        Avoid blocking I/O and long computations here.
        \"\"\"
        return None

    def on_unload(self, ctx: PluginAppContext) -> None:
        \"\"\"App-scope teardown.

        Disconnect signals/actions and stop app-scoped services started in `on_load`.
        \"\"\"
        return None
{_focus_hooks_template(include=req.kind == PluginKind.WORKSPACE)}

    def on_project_migrate(self, ctx: PluginProjectContext) -> PluginFutureResult:
        \"\"\"Project-scope DB migrations (runs before `on_project_opened`).\"\"\"
        return ctx.db.plugin_meta_set(plugin_version=ctx.plugin.version, schema_version=1)

    def on_project_opened(self, ctx: PluginProjectContext) -> PluginFutureResult:
        \"\"\"Project-scope setup.

        Start watchers/pipelines and restore state from `ctx.db.kv_get(...)`.
        \"\"\"
        return None

    def on_project_closing(self, ctx: PluginProjectContext) -> PluginFutureResult:
        \"\"\"Project-scope teardown.

        Stop pipelines and return Futures representing flush/shutdown work so core can await them.
        \"\"\"
        return None


def get_plugin() -> BasePlugin:
    return {class_name}()
"""

def _package_init_template(*, name: str) -> str:
    return f'''"""Plugin package: {name}.

This plugin is loaded by DataLens via `manifest.json` and `plugin.py`.
Subpackages may be generated depending on the plugin kind:

- `ui/`: widgets/panels for workspace UI (WORKSPACE plugins)
- `services/`: plugin logic/use-cases (SERVICE/DATASOURCE/MODEL plugins)
"""
'''


def _ui_package_init_template() -> str:
    return '''"""UI package for this plugin.

Put widgets and panels here. Keep non-trivial logic in `services/`.
"""
'''


def _services_package_init_template() -> str:
    return '''"""Services package for this plugin.

Put non-trivial logic here (pipelines, background work orchestration, etc.).
Avoid importing Qt widgets from this package.
"""
'''


def _ui_workspace_stub(*, plugin_id: str) -> str:
    return f"""from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout


class WorkspaceWidget(QWidget):
    \"\"\"Placeholder workspace UI for `{plugin_id}`.\"\"\"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel({plugin_id!r}))
"""


def _services_stub() -> str:
    return """from __future__ import annotations


class PluginService:
    \"\"\"Placeholder for app/project-scoped plugin services.\"\"\"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None
"""


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
    (plugin_root / "__init__.py").write_text(_package_init_template(name=request.name), encoding="utf-8")

    # Create subpackages only where we provide scaffolding that matches the plugin kind.
    if request.kind == PluginKind.WORKSPACE:
        ui_dir = plugin_root / "ui"
        ui_dir.mkdir(exist_ok=False)
        (ui_dir / "__init__.py").write_text(_ui_package_init_template(), encoding="utf-8")
        (ui_dir / "workspace.py").write_text(_ui_workspace_stub(plugin_id=request.plugin_id), encoding="utf-8")
    else:
        services_dir = plugin_root / "services"
        services_dir.mkdir(exist_ok=False)
        (services_dir / "__init__.py").write_text(_services_package_init_template(), encoding="utf-8")
        (services_dir / "service.py").write_text(_services_stub(), encoding="utf-8")

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
