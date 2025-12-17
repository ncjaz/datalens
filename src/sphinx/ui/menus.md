# Menu system (V2)

This page documents how the **main app menu bar** is structured in V2, and how to add new menu items without bloating a single file.

Scope:

- This is currently a **core app developer** workflow.
- We intend to evolve this so **plugins can contribute menu items** later (see “Planned: plugin menu contributions”).

## Goals

- Keep `menubar.py` small and stable (no dialogs/services imported there).
- Keep each menu independently maintainable (File/Edit/Plugins/Help can grow without merging conflicts).
- Keep UI actions and “what they do” separated:
  - `menu.py` declares actions (`QAction`) and where they appear.
  - `controller.py` implements behavior (open dialogs, call services, run loaders).
- Avoid `MainWindow` bloat by keeping menu composition in a small factory.

## Current structure

Files:

- Composition (dependency injection):
  - `datalens.ui.menus.factory.create_menubar`
- Menu bar skeleton:
  - `datalens.ui.menus.menubar.DatalensMenuBar`
- Contracts (interfaces between menu and behavior):
  - `datalens.ui.menus.contracts`
- Per-menu modules:
  - `datalens.ui.menus.file.menu` + `datalens.ui.menus.file.controller`
  - `datalens.ui.menus.edit.menu` + `datalens.ui.menus.edit.controller`
  - `datalens.ui.menus.plugins.menu` + `datalens.ui.menus.plugins.controller`
  - `datalens.ui.menus.help.menu` + `datalens.ui.menus.help.controller`

### Data flow

1. `MainWindow` calls `create_menubar(self)` and sets it with `self.setMenuBar(...)`.
2. The factory creates concrete controllers and injects them into `DatalensMenuBar`.
3. `DatalensMenuBar` creates top-level menus (`File`, `Edit`, `Plugins`, `Help`) and delegates population to each menu module.
4. Each `menu.py` connects its `QAction.triggered` to a method on its controller.

`contracts.py` does not execute anything; it defines the “shape” (Protocols) for controllers so menus don’t need to import implementations.

## Walkthrough: Preferences (Edit → Preferences…)

Preferences is the first worked example of this system.

### Where the UI lives

- Dialog UI:
  - `datalens.ui.menus.edit.preferences.preferences_dialog.PreferencesDialog`
- Example page:
  - `datalens.ui.menus.edit.preferences.pages.file_paths.FilePathsPage`

Preferences dialog UI state (geometry, splitter, last page) is stored using `QSettingsScope` (UI-only persistence), while semantic settings should be persisted via `SettingsStore` / `DebouncedSettingsWriter`.

### Where the menu item is declared

- Edit menu declaration:
  - `datalens.ui.menus.edit.menu.populate`

It creates `QAction("Preferences…")` and connects it to `EditMenuController.open_preferences()`.

### Where behavior is implemented

- Edit menu controller:
  - `datalens.ui.menus.edit.controller.QtEditMenuController.open_preferences`

The controller:

- constructs `PreferencesDialog` on first use
- reuses a single instance while it is open
- clears the cached reference when the dialog finishes

## Step-by-step: add a new action under Edit (“Models…”)

This example creates a new window and adds `Edit → Models…`.

### 1) Create the UI module

Create a new widget/window (choose dialog vs window based on UX):

- `datalens/src/datalens/ui/menus/edit/models/models_window.py`

Keep it UI-only; put non-trivial logic in `datalens/services/...` and call into it.

### 2) Add the menu item

Edit:

- `datalens/src/datalens/ui/menus/edit/menu.py`

Add the action and connect it to the controller method.

### 3) Add the controller interface method

Edit:

- `datalens/src/datalens/ui/menus/contracts.py`

Add `open_models(self) -> None` to `EditMenuController`.

(This keeps `menu.py` type-safe; if this becomes too noisy, we can switch Edit to an action-id dispatch table.)

### 4) Implement the behavior in the controller

Edit:

- `datalens/src/datalens/ui/menus/edit/controller.py`

Implement `open_models()`:

- create the window (parent it to the main window)
- show/raise/activate it
- keep a single instance cached if appropriate (same pattern as Preferences)

### 5) Wire any dependencies in the factory (if needed)

If the Models window needs additional dependencies (services, registries), inject them via the controller constructor and provide them from:

- `datalens/src/datalens/ui/menus/factory.py`

Keep `MainWindow` out of this wiring.

## Planned: plugin menu contributions

We currently build the menu tree from core code only. To support plugins adding menu items safely and consistently, V2 likely needs:

- a registry for menu actions (“ActionRegistry” or capability-based contributions)
- an explicit contract for where plugins may attach (e.g. `Plugins` menu or a per-plugin submenu)
- rules for threading (handlers must not block the UI thread; use loader/IoWriter/ProjectDb for long work)

Until that is implemented, plugins should not modify the menu bar directly.

