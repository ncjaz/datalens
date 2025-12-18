# UI widgets

DataLens V2 provides a small set of reusable, theme-aware widgets under `datalens.ui.widgets`.

If you are building UI in core or in a plugin, prefer these widgets over bespoke QSS so the app stays consistent and
theme changes apply everywhere.

## Theme and styling

- Theme wrapper: {py:class}`datalens.ui.theme.app_theme.AppTheme`
- Theme tokens: {py:class}`datalens.domain.ui.theme.ThemeSettings`
- Opacity policy: {py:class}`datalens.domain.ui.theme.ThemeOpacitySettings`

Most “standard” widgets are styled via QSS and use {py:class}`datalens.ui.widgets.core.styled.StyledMixin` for:

- pill radius + padding defaults
- selected/hover/background color resolution

## Buttons

Module: {py:mod}`datalens.ui.widgets.core.buttons`

The primary button class is {py:class}`datalens.ui.widgets.core.buttons.DatalensButton`.

Use semantic variants so the intent is obvious:

```python
from datalens.ui.widgets.core.buttons import DatalensButton, ButtonVariant

ok_btn = DatalensButton("OK", theme, ButtonVariant.CONFIRM)
danger_btn = DatalensButton("Delete", theme, ButtonVariant.CANCEL)
```

### Outlined buttons (optional)

`DatalensButton` supports an outlined mode via a flag:

```python
outlined = DatalensButton("Secondary", theme, ButtonVariant.SECONDARY, outlined=True)
```

Outlined buttons use the theme’s border tokens:

- `ThemeSettings.primary_border`, `secondary_border`, `tertiary_border`
- `ThemeSettings.accent_confirm_border`, `accent_cancel_border`, `accent_warning_border`

Default behavior stays unchanged unless `outlined=True` is used.

## Toggles

Module: {py:mod}`datalens.ui.widgets.core.toggle`

Use {py:class}`datalens.ui.widgets.core.toggle.Toggle` for pill-style two-option toggles.

```python
from datalens.ui.widgets.core.toggle import Toggle, ToggleOption

toggle = Toggle(
    theme=theme,
    options=(ToggleOption("Off", "off"), ToggleOption("On", "on")),
    selected="off",
)
```

## Checkboxes

Module: {py:mod}`datalens.ui.widgets.core.checkboxes`

Use {py:class}`datalens.ui.widgets.core.checkboxes.DatalensCheckBox` for theme-consistent checkbox styling.

## Icons

Icons live under `datalens.ui.widgets.icons`.

- Prefer these icons over Qt standard icons for product consistency.
- Icons should be usable from both core UI and plugins.

## Loader dialog widget

UI: {py:class}`datalens.ui.widgets.dialogs.loader_dialog.LoaderDialog`

The loader system is documented separately:

- {doc}`loader`

## See also

- API reference: `datalens/src/sphinx/api/ui.rst`
- Widget gallery workspace (for manual visual checks): `datalens.plugins.widget_test`
