from __future__ import annotations

"""
Plugin preferences schema (manifest-driven, metadata-only).

This module is part of the *domain* layer:
- Qt-free
- I/O-free
- JSON-serializable

It enables building Preferences UI pages for plugins without importing plugin
runtime code (works even when a plugin is disabled).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PreferenceKind(str, Enum):
    BOOL = "bool"
    ENUM = "enum"
    TOGGLE = "toggle"  # 2-option enum rendered as a Toggle widget
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    PATH = "path"


class PathKind(str, Enum):
    FILE = "file"
    DIR = "dir"


def _as_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    out = value.strip()
    if not out:
        raise ValueError(f"{field_name} must be non-empty")
    return out


def _as_opt_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    out = value.strip()
    return out or None


@dataclass(frozen=True)
class PreferenceOption:
    """Option for `enum` and `toggle` fields."""

    id: str
    label: str

    @staticmethod
    def from_dict(data: object) -> "PreferenceOption":
        if not isinstance(data, dict):
            raise TypeError("option must be an object")
        return PreferenceOption(
            id=_as_str(data.get("id"), field_name="option.id"),
            label=_as_str(data.get("label"), field_name="option.label"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label}


@dataclass(frozen=True)
class PreferenceField:
    """
    A single plugin preference field definition.

    `key` is persisted under:
      settings.plugin_settings[plugin_id][key] = value
    """

    key: str
    title: str
    kind: PreferenceKind
    description: str | None = None
    default: object | None = None
    options: tuple[PreferenceOption, ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    path_kind: PathKind | None = None

    @staticmethod
    def from_dict(data: object) -> "PreferenceField":
        if not isinstance(data, dict):
            raise TypeError("field must be an object")

        key = _as_str(data.get("key"), field_name="field.key")
        title = _as_str(data.get("title"), field_name="field.title")
        kind_raw = _as_str(data.get("kind"), field_name="field.kind")
        try:
            kind = PreferenceKind(kind_raw)
        except Exception as exc:
            raise ValueError(f"Unknown field.kind {kind_raw!r}") from exc

        description = _as_opt_str(data.get("description"), field_name="field.description")
        default = data.get("default")

        options: tuple[PreferenceOption, ...] = ()
        if kind in (PreferenceKind.ENUM, PreferenceKind.TOGGLE):
            raw = data.get("options", [])
            if raw is None:
                raw = []
            if not isinstance(raw, list):
                raise TypeError("field.options must be a list")
            options = tuple(PreferenceOption.from_dict(item) for item in raw)
            if kind == PreferenceKind.TOGGLE and len(options) != 2:
                raise ValueError("toggle fields must have exactly 2 options")

        min_value = data.get("min")
        max_value = data.get("max")
        step = data.get("step")

        def _as_float(v: object | None, *, name: str) -> float | None:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v.strip():
                try:
                    return float(v)
                except ValueError as exc:
                    raise ValueError(f"{name} must be numeric") from exc
            raise ValueError(f"{name} must be numeric")

        min_v = _as_float(min_value, name="field.min")
        max_v = _as_float(max_value, name="field.max")
        step_v = _as_float(step, name="field.step")

        path_kind: PathKind | None = None
        if kind == PreferenceKind.PATH:
            raw = data.get("path_kind", PathKind.FILE.value)
            if raw is None:
                raw = PathKind.FILE.value
            if not isinstance(raw, str):
                raw = str(raw)
            raw = raw.strip().lower() or PathKind.FILE.value
            try:
                path_kind = PathKind(raw)
            except Exception as exc:
                raise ValueError(f"Unknown field.path_kind {raw!r}") from exc

        return PreferenceField(
            key=key,
            title=title,
            kind=kind,
            description=description,
            default=default,
            options=options,
            min_value=min_v,
            max_value=max_v,
            step=step_v,
            path_kind=path_kind,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "title": self.title,
            "kind": self.kind.value,
        }
        if self.description:
            out["description"] = self.description
        if self.default is not None:
            out["default"] = self.default
        if self.options:
            out["options"] = [o.to_dict() for o in self.options]
        if self.min_value is not None:
            out["min"] = self.min_value
        if self.max_value is not None:
            out["max"] = self.max_value
        if self.step is not None:
            out["step"] = self.step
        if self.path_kind is not None:
            out["path_kind"] = self.path_kind.value
        return out


@dataclass(frozen=True)
class PreferenceSection:
    id: str
    title: str
    fields: tuple[PreferenceField, ...] = ()
    description: str | None = None
    collapsed: bool = False

    @staticmethod
    def from_dict(data: object) -> "PreferenceSection":
        if not isinstance(data, dict):
            raise TypeError("section must be an object")
        raw_fields = data.get("fields", [])
        if raw_fields is None:
            raw_fields = []
        if not isinstance(raw_fields, list):
            raise TypeError("section.fields must be a list")
        return PreferenceSection(
            id=_as_str(data.get("id"), field_name="section.id"),
            title=_as_str(data.get("title"), field_name="section.title"),
            fields=tuple(PreferenceField.from_dict(item) for item in raw_fields),
            description=_as_opt_str(data.get("description"), field_name="section.description"),
            collapsed=bool(data.get("collapsed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "title": self.title, "fields": [f.to_dict() for f in self.fields]}
        if self.description:
            out["description"] = self.description
        if self.collapsed:
            out["collapsed"] = True
        return out


@dataclass(frozen=True)
class PluginPreferencesSchema:
    """
    Schema container stored in a plugin manifest under `preferences`.

    v0 schema is JSON-only (manifest), represented here in dataclasses.
    """

    version: int = 0
    sections: tuple[PreferenceSection, ...] = field(default_factory=tuple)

    @staticmethod
    def from_dict(data: object) -> "PluginPreferencesSchema":
        if data is None:
            return PluginPreferencesSchema()
        if not isinstance(data, dict):
            raise TypeError("preferences must be an object")
        # Manifest uses `schema_version`; accept `version` as an alias to keep the
        # parser tolerant (plugins may evolve independently of core examples).
        version_raw = data.get("schema_version", data.get("version", 0))
        version = int(version_raw) if isinstance(version_raw, (int, float, str)) else 0
        raw_sections = data.get("sections", [])
        if raw_sections is None:
            raw_sections = []
        if not isinstance(raw_sections, list):
            raise TypeError("preferences.sections must be a list")
        sections = tuple(PreferenceSection.from_dict(item) for item in raw_sections)
        return PluginPreferencesSchema(version=max(0, version), sections=sections)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": int(self.version), "sections": [s.to_dict() for s in self.sections]}


__all__ = [
    "PathKind",
    "PluginPreferencesSchema",
    "PreferenceField",
    "PreferenceKind",
    "PreferenceOption",
    "PreferenceSection",
]
