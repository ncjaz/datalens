from __future__ import annotations

from dataclasses import replace
import time
from typing import Any, Callable

from datalens.core.events import EventHub, PluginPreferencesChanged
from datalens.core.logging import get_logger
from datalens.domain.plugin import PluginId
from datalens.domain.plugin.preferences_schema import PluginPreferencesSchema, PreferenceField, PreferenceKind
from datalens.domain.system.settings import AppSettings
from datalens.services.settings_store import DebouncedSettingsWriter, SettingsStore, default_debounced_settings_writer, default_settings_store


log = get_logger(__name__)


PluginSettings = dict[str, object]
PluginSettingsSnapshot = dict[str, dict[str, object]]
SchemaResolver = Callable[[PluginId], PluginPreferencesSchema | None]
PluginPreferencesListener = Callable[[PluginId, set[str]], None]


def _coerce_value(field: PreferenceField, value: object) -> object:
    kind = field.kind

    if kind == PreferenceKind.BOOL:
        return bool(value)

    if kind in (PreferenceKind.ENUM, PreferenceKind.TOGGLE):
        v = str(value)
        allowed = {o.id for o in field.options}
        if allowed and v not in allowed:
            raise ValueError(f"Invalid value for {field.key}: {v!r} (allowed: {sorted(allowed)})")
        return v

    if kind == PreferenceKind.INT:
        iv = int(value)
        if field.min_value is not None:
            iv = max(iv, int(field.min_value))
        if field.max_value is not None:
            iv = min(iv, int(field.max_value))
        return iv

    if kind == PreferenceKind.FLOAT:
        fv = float(value)
        if field.min_value is not None:
            fv = max(fv, float(field.min_value))
        if field.max_value is not None:
            fv = min(fv, float(field.max_value))
        return fv

    if kind in (PreferenceKind.STRING, PreferenceKind.PATH):
        return str(value)

    if kind == PreferenceKind.COLOR:
        if not isinstance(value, dict):
            raise TypeError(f"{field.key} must be an object")

        def _clamp_byte(v: object, *, name: str) -> int:
            try:
                iv = int(v)
            except Exception as exc:
                raise TypeError(f"{field.key}.{name} must be an int") from exc
            return max(0, min(255, iv))

        def _clamp_opacity(v: object) -> float:
            try:
                fv = float(v)
            except Exception as exc:
                raise TypeError(f"{field.key}.opacity must be a number") from exc
            return max(0.0, min(1.0, fv))

        theme_ref_raw = value.get("theme_reference")
        theme_ref = str(theme_ref_raw).strip() if isinstance(theme_ref_raw, str) else None
        if theme_ref == "":
            theme_ref = None

        return {
            "r": _clamp_byte(value.get("r", 0), name="r"),
            "g": _clamp_byte(value.get("g", 0), name="g"),
            "b": _clamp_byte(value.get("b", 0), name="b"),
            "opacity": _clamp_opacity(value.get("opacity", 1.0)),
            "theme_reference": theme_ref,
        }

    return value


class PluginPreferencesService:
    """
    Plugin preferences (semantic, persisted) service.

    Goals:
    - Store plugin settings under `AppSettings.plugin_settings[plugin_id][key]`.
    - Never block the UI thread on disk IO (writes are debounced + background).
    - Provide change notifications via EventHub (queued delivery).
    - Provide a single JSON-serializable snapshot for diagnostics/States UI.
    """

    def __init__(
        self,
        *,
        events: EventHub,
        store: SettingsStore | None = None,
        writer: DebouncedSettingsWriter | None = None,
        schema_resolver: SchemaResolver | None = None,
    ) -> None:
        self._events = events
        self._store = store or default_settings_store()
        self._writer = writer or default_debounced_settings_writer()
        self._schema_resolver = schema_resolver

        self._settings: AppSettings | None = None
        self._version = 0

    def version(self) -> int:
        """Monotonic version incremented on preference changes (for diagnostics UIs)."""
        return int(self._version)

    def apply_settings(self, settings: AppSettings) -> None:
        """
        Seed/refresh the in-memory cache from an already-loaded AppSettings instance.

        The caller should invoke this after loading settings in a background task
        (startup, welcome->main transition, etc.) so UI reads never hit disk.
        """
        self._settings = settings
        self._version += 1

    def set_schema_resolver(self, resolver: SchemaResolver | None) -> None:
        """Update the schema resolver (best-effort; can be set after AppContext wiring)."""
        self._schema_resolver = resolver

    def _ensure_settings_cached(self) -> AppSettings:
        settings = self._settings
        if settings is not None:
            return settings
        # Fallback: load from disk. This may be called from UI if `apply_settings`
        # wasn't invoked; log so we can fix call sites.
        log.warning(
            "PluginPreferencesService cache miss; loading settings from disk (best-effort)",
            extra={"operation": "plugin_prefs", "phase": "cache_miss"},
        )
        settings = self._store.load()
        self._settings = settings
        return settings

    def _schema_for(self, plugin_id: PluginId) -> PluginPreferencesSchema | None:
        resolver = self._schema_resolver
        if resolver is None:
            return None
        try:
            return resolver(plugin_id)
        except Exception:
            log.debug("Schema resolver failed (best-effort)", exc_info=True)
            return None

    def _field_for(self, plugin_id: PluginId, key: str) -> PreferenceField | None:
        schema = self._schema_for(plugin_id)
        if schema is None:
            return None
        target = str(key).strip()
        for section in schema.sections:
            for field in section.fields:
                if field.key == target:
                    return field
        return None

    def get_plugin_raw(self, plugin_id: PluginId) -> dict[str, object]:
        settings = self._ensure_settings_cached()
        bucket = dict(getattr(settings, "plugin_settings", {}).get(str(plugin_id), {}) or {})
        return {str(k): v for k, v in bucket.items()}

    def get(self, plugin_id: PluginId, key: str, *, default: object | None = None) -> object | None:
        k = str(key).strip()
        if not k:
            return default
        raw = self.get_plugin_raw(plugin_id).get(k, None)
        if raw is None:
            field = self._field_for(plugin_id, k)
            if field is not None and field.default is not None:
                return field.default
            return default

        field = self._field_for(plugin_id, k)
        if field is None:
            return raw
        try:
            return _coerce_value(field, raw)
        except Exception:
            log.debug(
                "Invalid stored preference value (best-effort; falling back to default)",
                exc_info=True,
                extra={"operation": "plugin_prefs", "phase": "coerce_error", "plugin_id": str(plugin_id), "key": k},
            )
            if field.default is not None:
                return field.default
            return default

    def set(self, plugin_id: PluginId, key: str, value: object) -> None:
        k = str(key).strip()
        if not k:
            raise ValueError("Preference key must be non-empty")

        field = self._field_for(plugin_id, k)
        if field is not None:
            value = _coerce_value(field, value)

        current = self._ensure_settings_cached()
        plugin_settings = {pid: dict(values) for pid, values in dict(current.plugin_settings or {}).items()}
        bucket = dict(plugin_settings.get(str(plugin_id), {}))
        prior = bucket.get(k, None)
        if prior == value:
            return
        bucket[k] = value
        plugin_settings[str(plugin_id)] = bucket
        updated = replace(current, plugin_settings=plugin_settings)
        self._settings = updated
        self._version += 1

        self._writer.request_save(updated)
        self._events.publish(
            EventHub.PLUGIN_PREFERENCES_CHANGED,
            PluginPreferencesChanged(plugin_id=PluginId(str(plugin_id)), changed_keys=(k,), timestamp_s=time.time()),
        )

    def replace_plugin(self, plugin_id: PluginId, values: dict[str, object]) -> None:
        current = self._ensure_settings_cached()
        plugin_settings = {pid: dict(v) for pid, v in dict(current.plugin_settings or {}).items()}
        prior = dict(plugin_settings.get(str(plugin_id), {}))
        next_bucket: dict[str, object] = {str(k): v for k, v in dict(values).items()}

        # Validate/coerce if schema exists
        schema = self._schema_for(plugin_id)
        if schema is not None:
            coerced: dict[str, object] = {}
            for section in schema.sections:
                for field in section.fields:
                    if field.key in next_bucket:
                        coerced[field.key] = _coerce_value(field, next_bucket[field.key])
            # Keep unknown keys as-is (forward compatible).
            for k, v in next_bucket.items():
                coerced.setdefault(k, v)
            next_bucket = coerced

        if prior == next_bucket:
            return

        plugin_settings[str(plugin_id)] = next_bucket
        updated = replace(current, plugin_settings=plugin_settings)
        self._settings = updated
        self._version += 1

        changed = {k for k in set(prior.keys()) | set(next_bucket.keys()) if prior.get(k) != next_bucket.get(k)}
        self._writer.request_save(updated)
        self._events.publish(
            EventHub.PLUGIN_PREFERENCES_CHANGED,
            PluginPreferencesChanged(
                plugin_id=PluginId(str(plugin_id)),
                changed_keys=tuple(sorted(changed)),
                timestamp_s=time.time(),
            ),
        )

    def reset_to_defaults(self, plugin_id: PluginId) -> None:
        schema = self._schema_for(plugin_id)
        if schema is None:
            self.replace_plugin(plugin_id, {})
            return
        defaults: dict[str, object] = {}
        for section in schema.sections:
            for field in section.fields:
                if field.default is not None:
                    defaults[field.key] = field.default
        self.replace_plugin(plugin_id, defaults)

    def subscribe(self, plugin_id: PluginId, listener: PluginPreferencesListener) -> Callable[[], None]:
        """
        Subscribe to preference changes for one plugin.

        Listener is invoked on the UI thread (EventHub queued delivery).
        """

        pid = PluginId(str(plugin_id))

        def _on_event(payload: object) -> None:
            if not isinstance(payload, PluginPreferencesChanged):
                return
            if PluginId(str(payload.plugin_id)) != pid:
                return
            listener(pid, set(payload.changed_keys))

        sub = self._events.subscribe(EventHub.PLUGIN_PREFERENCES_CHANGED, _on_event)
        return sub.unsubscribe

    def snapshot(self) -> dict[str, Any]:
        """
        Return a JSON-serializable snapshot of effective plugin preferences.

        This is the single source of truth for the States inspector and any
        capability-based "preferences view" consumers.
        """
        settings = self._ensure_settings_cached()
        raw_all = dict(settings.plugin_settings or {})
        out: dict[str, Any] = {"plugins": {}}
        for pid, raw_values in raw_all.items():
            plugin_id = PluginId(str(pid))
            values: dict[str, Any] = {}
            bucket = dict(raw_values or {})
            schema = self._schema_for(plugin_id)
            if schema is not None:
                for section in schema.sections:
                    for field in section.fields:
                        if field.key in bucket:
                            try:
                                values[field.key] = _coerce_value(field, bucket[field.key])
                            except Exception:
                                values[field.key] = field.default
                        else:
                            values[field.key] = field.default
                # Preserve unknown keys for forward compatibility.
                for k, v in bucket.items():
                    values.setdefault(str(k), v)
            else:
                values = {str(k): v for k, v in bucket.items()}
            out["plugins"][str(pid)] = values
        return out


__all__ = ["PluginPreferencesService"]
