from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QLabel,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)

from .registry import ShortcutRowsBuilder
from .types import RebuildResult


def rebuild_shortcuts_ui(
    *,
    dynamic_container: QWidget,
    dynamic_layout: QVBoxLayout,
    conflicts_label: QLabel,
    snap: object,
    filter_key: str | None,
    mode_is_keyboard_only: Callable[[object, object], bool],
    on_binding_changed: Callable[[str, str, str, object], None],
    on_binding_reset: Callable[[str, str, str], None],
    on_consume_changed: Callable[[str, str, str, bool], None],
    on_consume_reset: Callable[[str, str, str], None],
    on_recording_changed: Callable[[bool], None],
    on_mode_changed: Callable[[str, str, bool], None],
    on_mode_reset: Callable[[str, str], None],
) -> RebuildResult:
    """
    Rebuild the dynamic content area for the keyboard shortcuts preferences page.

    `snap` is the shortcuts snapshot returned by the shortcuts service. We keep it
    untyped here so the UI layer does not need to import internal snapshot types.
    """
    for i in reversed(range(dynamic_layout.count())):
        item = dynamic_layout.takeAt(i)
        w = item.widget()
        if w is not None:
            w.deleteLater()

    result = RebuildResult(
        plugin_boxes={},
        editors={},
        consume_checks={},
        consume_reset_buttons={},
        mode_toggles={},
        mode_reset_buttons={},
        mode_defaults={},
        binding_scopes={},
        last_saved={},
    )

    conflicts = getattr(snap, "conflicts", []) or []
    if conflicts:
        lines: list[str] = []
        for c in conflicts[:8]:
            ids = ", ".join(getattr(c, "binding_ids", []) or [])
            lines.append(f"{getattr(c, 'plugin_id', '?')}: {getattr(c, 'chord', '?')} ({ids})")
        more = "" if len(conflicts) <= 8 else f"\n... and {len(conflicts) - 8} more"
        conflicts_label.setText(
            "Conflicting bindings detected (only the first binding will be active for a chord/scope):\n"
            + "\n".join(lines)
            + more
        )
        conflicts_label.show()
    else:
        conflicts_label.hide()

    pages = getattr(snap, "pages", None) or []
    if not pages:
        empty = QLabel("No shortcut pages are registered yet.", dynamic_container)
        dynamic_layout.addWidget(empty)
        return result

    pages = sorted(pages, key=lambda p: (p.get("plugin_name", ""), p.get("page_title", "")))
    by_plugin: dict[str, list[dict]] = {}
    for page in pages:
        by_plugin.setdefault(str(page["plugin_id"]), []).append(page)

    rows = ShortcutRowsBuilder(
        result=result,
        mode_is_keyboard_only=mode_is_keyboard_only,
        on_binding_changed=on_binding_changed,
        on_binding_reset=on_binding_reset,
        on_consume_changed=on_consume_changed,
        on_consume_reset=on_consume_reset,
        on_recording_changed=on_recording_changed,
        on_mode_changed=on_mode_changed,
        on_mode_reset=on_mode_reset,
    )

    for plugin_id, plugin_pages in sorted(by_plugin.items(), key=lambda kv: kv[1][0].get("plugin_name", kv[0])):
        plugin_name = plugin_pages[0].get("plugin_name", plugin_id)
        plugin_box = QGroupBox(str(plugin_name), dynamic_container)
        plugin_box.setObjectName(f"KeyboardShortcutsPlugin:{plugin_id}")
        plugin_layout = QVBoxLayout(plugin_box)
        plugin_layout.setContentsMargins(12, 10, 12, 12)
        plugin_layout.setSpacing(12)
        result.plugin_boxes[str(plugin_id)] = plugin_box

        for page in plugin_pages:
            page_title = page.get("page_title") or "Shortcuts"
            page_label = QLabel(str(page_title), plugin_box)
            page_label.setStyleSheet("font-weight: 600;")
            plugin_layout.addWidget(page_label)

            for section in page.get("sections", []):
                section_box = QGroupBox(str(section.get("section_title") or "Commands"), plugin_box)
                section_layout = QFormLayout(section_box)
                section_layout.setContentsMargins(12, 10, 12, 12)
                section_layout.setHorizontalSpacing(12)
                section_layout.setVerticalSpacing(8)

                for cmd in section.get("commands", []):
                    rows.add_command_row(
                        section_layout,
                        plugin_id=plugin_id,
                        command_id=str(cmd["command_id"]),
                        title=str(cmd.get("title") or str(cmd["command_id"])),
                        description=str(cmd.get("description") or ""),
                        scope=str(cmd.get("scope") or "workspace"),
                        default_chord=cmd.get("default_chord"),
                        effective_chord=cmd.get("effective_chord"),
                        is_overridden=bool(cmd.get("is_overridden", False)),
                        consume_event=bool(cmd.get("consume_event", False)),
                        mode_toggle_default=cmd.get("mode_toggle_default"),
                        mode_toggle_effective=cmd.get("mode_toggle"),
                    )

                for g in section.get("gestures", []):
                    rows.add_gesture_row(
                        section_layout,
                        plugin_id=plugin_id,
                        gesture_id=str(g["gesture_id"]),
                        title=str(g.get("title") or str(g["gesture_id"])),
                        description=str(g.get("description") or ""),
                        scope=str(g.get("scope") or "workspace"),
                        default_chord=g.get("default_chord"),
                        effective_chord=g.get("effective_chord"),
                        is_overridden=bool(g.get("is_overridden", False)),
                        uses_modifier_defaults=bool(g.get("uses_modifier_defaults", False)),
                        consume_event=bool(g.get("consume_event", True)),
                    )

                plugin_layout.addWidget(section_box)

        dynamic_layout.addWidget(plugin_box)
        if filter_key and str(plugin_id) != filter_key:
            plugin_box.hide()

    dynamic_layout.addStretch(1)
    return result


__all__ = ["rebuild_shortcuts_ui"]
