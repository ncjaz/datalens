from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalens.core.logging import get_logger
from datalens.domain.plugin import (
    PluginDefinition,
    PluginFeature,
    PluginGroupId,
    PluginId,
    PluginKind,
    PluginStage,
)
from datalens.infra.paths import user_plugins_dir
from datalens.services.plugins.registry import PluginLocation, PluginOrigin, PluginRecord, PluginRegistry, PluginRequirements


log = get_logger(__name__)


@dataclass(frozen=True)
class PluginDiscoveryIssue:
    plugin_dir: Path
    message: str


@dataclass(frozen=True)
class PluginDiscoveryResult:
    registry: PluginRegistry
    issues: tuple[PluginDiscoveryIssue, ...]


def _default_shipped_plugins_dir() -> Path:
    # datalens/services/plugins/loader.py -> datalens/ (parents[2]) -> plugins/
    return Path(__file__).resolve().parents[2] / "plugins"


def _read_requirements_txt(plugin_dir: Path) -> PluginRequirements:
    requirements_path = plugin_dir / "requirements.txt"
    if not requirements_path.exists():
        return PluginRequirements()

    lines: list[str] = []
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return PluginRequirements(pip_requirements=tuple(lines))


def _parse_feature(entry: Any) -> PluginFeature:
    if not isinstance(entry, dict):
        raise TypeError("feature entry must be an object")
    feature_id = entry.get("id")
    kind_raw = entry.get("kind")
    entrypoint = entry.get("entrypoint")
    display_name = entry.get("display_name") or entry.get("name")
    description = entry.get("description", "")

    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("feature.id must be a non-empty string")
    if not isinstance(kind_raw, str) or not kind_raw:
        raise ValueError("feature.kind must be a non-empty string")
    if not isinstance(entrypoint, str) or not entrypoint:
        raise ValueError("feature.entrypoint must be a non-empty string")
    if not isinstance(display_name, str) or not display_name:
        raise ValueError("feature.display_name must be a non-empty string")
    if not isinstance(description, str):
        description = str(description)

    try:
        kind = PluginKind(kind_raw)
    except Exception as exc:
        raise ValueError(f"Unknown feature.kind {kind_raw!r}") from exc

    return PluginFeature(
        id=feature_id,
        kind=kind,
        entrypoint=entrypoint,
        display_name=display_name,
        description=description,
    )


def _plugin_definition_from_manifest_json(*, plugin_dir: Path, builtin: bool) -> PluginDefinition:
    manifest_path = plugin_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("manifest.json must contain an object")

    plugin_id_raw = payload.get("id")
    name = payload.get("name")
    version = payload.get("version")
    description = payload.get("description", "")

    if not isinstance(plugin_id_raw, str) or not plugin_id_raw:
        raise ValueError("manifest.id must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise ValueError("manifest.name must be a non-empty string")
    if not isinstance(version, str) or not version:
        raise ValueError("manifest.version must be a non-empty string")
    if not isinstance(description, str):
        description = str(description)

    group_raw = payload.get("group")
    group = PluginGroupId(group_raw) if isinstance(group_raw, str) and group_raw else None

    stage_raw = payload.get("stage", "release")
    if stage_raw is None:
        stage_raw = "release"
    if not isinstance(stage_raw, str):
        stage_raw = str(stage_raw)
    try:
        stage = PluginStage(stage_raw)
    except Exception as exc:
        raise ValueError(f"Unknown manifest.stage {stage_raw!r}") from exc

    core_version_constraint = payload.get("core_version_constraint")
    if core_version_constraint is not None and not isinstance(core_version_constraint, str):
        core_version_constraint = str(core_version_constraint)

    author = payload.get("author")
    if author is not None and not isinstance(author, str):
        author = str(author)

    homepage = payload.get("homepage")
    if homepage is not None and not isinstance(homepage, str):
        homepage = str(homepage)

    manual_raw = payload.get("manual_pip_requirements", [])
    if manual_raw is None:
        manual_raw = []
    if not isinstance(manual_raw, list):
        raise TypeError("manifest.manual_pip_requirements must be a list of strings")
    manual_pip_requirements = tuple(str(v) for v in manual_raw if str(v).strip())

    enabled_by_default = payload.get("enabled_by_default", True)
    enabled_by_default = bool(enabled_by_default)

    features_raw = payload.get("features", [])
    if features_raw is None:
        features_raw = []
    if not isinstance(features_raw, list):
        raise TypeError("manifest.features must be a list")
    features = tuple(_parse_feature(entry) for entry in features_raw)

    return PluginDefinition(
        id=PluginId(plugin_id_raw),
        name=name,
        version=version,
        description=description,
        features=features,
        stage=stage,
        author=author,
        homepage=homepage,
        core_version_constraint=core_version_constraint,
        group=group,
        manual_pip_requirements=manual_pip_requirements,
        enabled_by_default=enabled_by_default,
        builtin=builtin,
    )


def _discover_plugins_under_root(*, root: Path, origin: PluginOrigin) -> tuple[list[PluginRecord], list[PluginDiscoveryIssue]]:
    records: list[PluginRecord] = []
    issues: list[PluginDiscoveryIssue] = []

    if not root.exists():
        return records, issues

    manifest_paths: list[Path] = []
    for path in root.rglob("manifest.json"):
        if any(part.startswith("__") for part in path.parts):
            continue
        manifest_paths.append(path)

    for manifest_path in sorted(manifest_paths, key=lambda p: str(p).lower()):
        plugin_dir = manifest_path.parent
        try:
            builtin = origin == PluginOrigin.SHIPPED
            definition = _plugin_definition_from_manifest_json(plugin_dir=plugin_dir, builtin=builtin)

            requirements = _read_requirements_txt(plugin_dir)
            location = PluginLocation(origin=origin, root_dir=plugin_dir)
            records.append(PluginRecord(definition=definition, location=location, requirements=requirements))
        except Exception as exc:
            issues.append(PluginDiscoveryIssue(plugin_dir=plugin_dir, message=str(exc)))

    return records, issues


def discover_plugins(
    *,
    shipped_plugins_dir: Path | None = None,
    user_plugins_root_dir: Path | None = None,
) -> PluginDiscoveryResult:
    """
    Discover plugins from builtin + user plugin directories.

    Discovery is intentionally "metadata-only": it reads manifests and optional
    `requirements.txt` without importing plugin runtime code.
    """

    shipped_root = shipped_plugins_dir or _default_shipped_plugins_dir()
    user_root = user_plugins_root_dir or user_plugins_dir()

    registry = PluginRegistry()
    issues: list[PluginDiscoveryIssue] = []

    shipped_records, shipped_issues = _discover_plugins_under_root(root=shipped_root, origin=PluginOrigin.SHIPPED)
    user_records, user_issues = _discover_plugins_under_root(root=user_root, origin=PluginOrigin.USER)
    issues.extend(shipped_issues)
    issues.extend(user_issues)

    for record in [*shipped_records, *user_records]:
        try:
            registry.register(record)
        except Exception as exc:
            issues.append(PluginDiscoveryIssue(plugin_dir=record.location.root_dir, message=str(exc)))

    result = PluginDiscoveryResult(registry=registry, issues=tuple(issues))
    log.info(
        "Discovered %s plugin(s) (%s issue(s))",
        len(result.registry.all()),
        len(result.issues),
        extra={"operation": "discover_plugins", "phase": "end"},
    )
    for issue in result.issues:
        log.warning(
            "Plugin discovery issue in %s: %s",
            issue.plugin_dir,
            issue.message,
            extra={"operation": "discover_plugins", "phase": "warning"},
        )
    return result
