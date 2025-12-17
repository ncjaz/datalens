from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class FileMenuController(Protocol):
    def new_project(self) -> None: ...
    def open_project(self) -> None: ...
    def open_recent_project(self, path: Path) -> None: ...
    def close_project(self) -> None: ...
    def quit_app(self) -> None: ...


class EditMenuController(Protocol):
    def open_preferences(self) -> None: ...


class PluginsMenuController(Protocol):
    def manage_plugins(self) -> None: ...
    def create_new_plugin(self) -> None: ...


class HelpMenuController(Protocol):
    def open_about(self) -> None: ...
    def open_states(self) -> None: ...


@dataclass(frozen=True)
class MenuControllers:
    file: FileMenuController
    edit: EditMenuController
    plugins: PluginsMenuController
    help: HelpMenuController
