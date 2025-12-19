from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from datalens.core.context import get_app_context
from datalens.core.events import EventHub
from datalens.domain.plugin import PluginId
from datalens.ui.qt_settings import QSettingsScope
from datalens.ui.menus.edit.preferences.pages.file_paths import FilePathsPage
from datalens.ui.menus.edit.preferences.pages.keyboard_shortcuts import KeyboardShortcutsPreferencesPage
from datalens.ui.menus.edit.preferences.pages.loader import LoaderPreferencesPage
from datalens.ui.menus.edit.preferences.pages.theme import ThemePreferencesPage
from datalens.ui.menus.edit.preferences.pages.user_interface import UserInterfacePreferencesPage


@dataclass(frozen=True)
class PreferencesPageSpec:
    key: str
    title: str
    widget: QWidget


class PreferencesDialog(QDialog):
    """
    Preferences dialog (Edit -> Preferences).

    Uses a left-side navigation list + right-side stacked pages to achieve
    "vertical tabs with horizontal text" (more flexible than QTabWidget-West).
    """

    applied = Signal()

    def __init__(self, parent: QWidget | None = None, *, initial_page_key: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(False)

        self._settings_scope = QSettingsScope(("ui", "preferences"))
        self._initial_page_key = initial_page_key

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Preferences")
        header.setObjectName("PreferencesHeader")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        self._splitter = splitter

        nav = QTreeWidget(splitter)
        nav.setObjectName("PreferencesNav")
        nav.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        nav.setFixedWidth(220)
        nav.setHeaderHidden(True)
        nav.setRootIsDecorated(True)
        nav.setIndentation(16)
        nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav = nav

        pages = QStackedWidget(splitter)
        pages.setObjectName("PreferencesPages")
        self._pages = pages

        self._page_specs: list[PreferencesPageSpec] = []
        self._key_to_index: dict[str, int] = {}
        self._dynamic_nav_parents: dict[str, QTreeWidgetItem] = {}
        self._dynamic_nav_providers: dict[str, object] = {}
        self._unsub_plugin_defs_changed: object | None = None

        ui_parent = self._add_nav_item("ui", "User Interface", None)
        self._add_page("ui", "User Interface", UserInterfacePreferencesPage())
        self._add_nav_item("ui.theme", "Theme", ui_parent)
        self._add_page("ui.theme", "Theme", ThemePreferencesPage())
        self._add_nav_item("ui.loader", "Loader", ui_parent)
        self._add_page("ui.loader", "Loader", LoaderPreferencesPage())

        self._add_nav_item("file_paths", "File Paths", None)
        self._add_page("file_paths", "File Paths", FilePathsPage())

        shortcuts_parent = self._add_nav_item("keyboard_shortcuts", "Keyboard Shortcuts", None)
        self._add_page("keyboard_shortcuts", "Keyboard Shortcuts", KeyboardShortcutsPreferencesPage())
        self._register_dynamic_children("keyboard_shortcuts", shortcuts_parent, self._shortcut_plugins_provider)
        self._subscribe_dynamic_nav_events()

        nav.currentItemChanged.connect(self._on_nav_changed)
        nav.expandAll()
        try:
            first = nav.topLevelItem(0)
            if first is not None:
                nav.setCurrentItem(first)
        except Exception:
            pass

        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            parent=self,
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)  # type: ignore[union-attr]
        root.addWidget(buttons)

        self._restore_ui_state()
        if self._initial_page_key:
            self.set_current_page(self._initial_page_key)

    def _subscribe_dynamic_nav_events(self) -> None:
        """
        Subscribe to semantic events that should trigger a nav rebuild.

        Example: editing a plugin `group` in Manage Plugins should immediately
        re-group the Keyboard Shortcuts children under the updated group names.
        """
        try:
            app_ctx = get_app_context()
        except Exception:
            return

        def on_defs_changed(_payload: object) -> None:
            try:
                self._refresh_dynamic_children()
                self._nav.expandAll()
            except Exception:
                return

        try:
            sub = app_ctx.events.subscribe(EventHub.PLUGIN_DEFINITIONS_CHANGED, on_defs_changed)
            self._unsub_plugin_defs_changed = sub.unsubscribe
        except Exception:
            self._unsub_plugin_defs_changed = None

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._refresh_dynamic_children()
        try:
            self._nav.expandAll()
        except Exception:
            pass

    def _register_dynamic_children(self, base_key: str, parent: QTreeWidgetItem, provider: object) -> None:
        """
        Register a dynamic child provider for a page.

        This is used for sections that can change during runtime (e.g. enabled plugins).
        `provider` must be callable and return an iterable of (child_key, title) pairs.
        """
        key = str(base_key).strip()
        if not key:
            return
        if not callable(provider):
            return
        self._dynamic_nav_parents[key] = parent
        self._dynamic_nav_providers[key] = provider

    def _refresh_dynamic_children(self) -> None:
        for base_key, parent in list(self._dynamic_nav_parents.items()):
            provider = self._dynamic_nav_providers.get(base_key)
            if parent is None or not callable(provider):
                continue
            try:
                while parent.childCount():
                    parent.removeChild(parent.child(0))
            except Exception:
                continue
            try:
                items = provider()
            except Exception:
                continue
            try:
                # Provider may return a group->children mapping for two-level nav.
                if isinstance(items, dict):
                    for group_title, children in items.items():
                        group_title = str(group_title).strip() or "Other"
                        # Group nodes are organizational only; selecting them shows the base page.
                        group_item = self._add_nav_item(base_key, group_title, parent)
                        for child_key, title in children:
                            child_key = str(child_key).strip()
                            title = str(title).strip()
                            if not child_key or not title:
                                continue
                            self._add_nav_item(f"{base_key}/{child_key}", title, group_item)
                else:
                    for child_key, title in items:
                        child_key = str(child_key).strip()
                        title = str(title).strip()
                        if not child_key or not title:
                            continue
                        self._add_nav_item(f"{base_key}/{child_key}", title, parent)
            except Exception:
                continue

    def _shortcut_plugins_provider(self) -> dict[str, list[tuple[str, str]]]:
        """
        Return group -> [(plugin_id, plugin_name)] for plugins that registered shortcut pages.

        Note: This only includes enabled plugins (disabled plugins are not imported).
        """
        out: dict[str, list[tuple[str, str]]] = {}
        snap = get_app_context().shortcuts.snapshot()
        if not snap.pages:
            return out
        plugin_name_by_id: dict[str, str] = {}
        for page in snap.pages:
            pid = str(page.get("plugin_id") or "").strip()
            if not pid:
                continue
            name = str(page.get("plugin_name") or pid).strip() or pid
            plugin_name_by_id.setdefault(pid, name)

        # Resolve grouping from the discovered registry (includes overrides).
        try:
            app_ctx = get_app_context()
            host = getattr(app_ctx, "plugin_host", None)
            registry = getattr(host, "registry", None) if host is not None else None
        except Exception:
            registry = None

        for plugin_id, plugin_name in plugin_name_by_id.items():
            group = "Other"
            if registry is not None:
                try:
                    record = registry.get(PluginId(plugin_id))
                    if record is not None:
                        raw = getattr(record.definition, "group", None)
                        if isinstance(raw, str) and raw.strip():
                            group = raw.strip()
                except Exception:
                    group = "Other"
            out.setdefault(group, []).append((plugin_id, plugin_name))

        for group, items in list(out.items()):
            out[group] = sorted(items, key=lambda kv: kv[1].lower())
        out = dict(sorted(out.items(), key=lambda kv: kv[0].lower()))
        return out

    def _add_nav_item(self, key: str, title: str, parent: QTreeWidgetItem | None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.UserRole, key)
        if parent is None:
            self._nav.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _add_page(self, key: str, title: str, widget: QWidget) -> None:
        spec = PreferencesPageSpec(key=key, title=title, widget=widget)
        self._page_specs.append(spec)

        # Pages can grow vertically (Theme, Loader settings, etc.). Wrap each
        # page in a scroll area so the dialog can be resized freely without
        # expanding to the full content height.
        scroll = QScrollArea(self._pages)
        scroll.setObjectName(f"PreferencesScroll:{key}")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(widget)

        index = self._pages.addWidget(scroll)
        self._key_to_index[key] = int(index)

    def _on_nav_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        key = current.data(0, Qt.UserRole)
        if not isinstance(key, str) or not key:
            return
        if "/" in key:
            base, child = key.split("/", 1)
            base = base.strip()
            child = child.strip()
            if base and child and base in self._key_to_index:
                idx = self._key_to_index.get(base)
                if idx is None:
                    return
                self._pages.setCurrentIndex(int(idx))
                self._apply_page_filter(base_key=base, filter_key=child)
                return

        idx = self._key_to_index.get(key)
        if idx is None:
            return
        self._pages.setCurrentIndex(int(idx))
        if key in self._dynamic_nav_providers:
            self._apply_page_filter(base_key=key, filter_key=None)

    def _apply_page_filter(self, *, base_key: str, filter_key: str | None) -> None:
        """
        Apply a child filter to a page if it supports it (best-effort).

        Pages can optionally implement:
        - `set_filter(filter_key: str | None) -> None`
        - `focus_item(filter_key: str) -> None`
        """
        idx = self._key_to_index.get(base_key)
        if idx is None:
            return
        container = self._pages.widget(int(idx))
        if container is None:
            return
        scroll = container if isinstance(container, QScrollArea) else container.findChild(QScrollArea)
        if scroll is None:
            return
        page = scroll.widget()
        if page is None:
            return
        set_filter = getattr(page, "set_filter", None)
        if callable(set_filter):
            try:
                set_filter(filter_key)
            except Exception:
                pass
        if filter_key:
            focus = getattr(page, "focus_item", None)
            if callable(focus):
                try:
                    focus(filter_key)
                except Exception:
                    return

    def _restore_ui_state(self) -> None:
        self._settings_scope.restore_geometry("geometry", self)
        self._settings_scope.restore_splitter("splitter", self._splitter)
        # Restore last selected page (best-effort).
        try:
            with self._settings_scope.open() as s:
                key = s.value("page_key")
            if isinstance(key, str) and key:
                # Search manually; keys are stored in item user data, not text.
                def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
                    if item.data(0, Qt.UserRole) == key:
                        return item
                    for i in range(item.childCount()):
                        found = walk(item.child(i))
                        if found is not None:
                            return found
                    return None

                for i in range(self._nav.topLevelItemCount()):
                    found = walk(self._nav.topLevelItem(i))
                    if found is not None:
                        self._nav.setCurrentItem(found)
                        break
        except Exception:
            pass

    def set_current_page(self, key: str) -> None:
        """
        Select a specific preferences page by key.

        Used by menu shortcuts (e.g., Edit -> Keyboard Shortcuts…).
        """
        target = str(key).strip()
        if not target:
            return

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.UserRole) == target:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self._nav.topLevelItemCount()):
            found = walk(self._nav.topLevelItem(i))
            if found is not None:
                self._nav.setCurrentItem(found)
                return

    def _persist_ui_state(self) -> None:
        self._settings_scope.save_geometry("geometry", self)
        self._settings_scope.save_splitter("splitter", self._splitter)
        try:
            item = self._nav.currentItem()
            key = item.data(0, Qt.UserRole) if item is not None else ""
            key = key if isinstance(key, str) else ""
            with self._settings_scope.open() as s:
                s.setValue("page_key", key)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        try:
            unsub = self._unsub_plugin_defs_changed
            self._unsub_plugin_defs_changed = None
            if callable(unsub):
                unsub()
        except Exception:
            pass
        self._persist_ui_state()
        super().closeEvent(event)

    def _on_apply(self) -> None:
        # Semantic settings are persisted by individual pages (typically via
        # SettingsStore/DebouncedSettingsWriter). `Apply` exists so the user can
        # keep the dialog open while committing changes.
        self._persist_ui_state()
        self.applied.emit()

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()
