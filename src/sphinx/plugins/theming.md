# Theming (colors + opacity)

V2 themes are built from two parts:

- **Color tokens** (`ThemeSettings`): opaque hex strings like `#RRGGBB`
- **Opacity policy** (`ThemeOpacitySettings`): standard alpha values for UI states

This keeps the app consistent while still allowing per-plugin overrides.

## Where theme lives

- Domain tokens: `datalens.domain.ui.theme.ThemeSettings` and `ThemeOpacitySettings`
- Qt-friendly wrapper used by widgets: `datalens.ui.theme.app_theme.AppTheme`

Plugins should *not* import other plugins to share styling. Use `AppTheme`
provided by the application/plugin context.

For icon styling rules, see `iconography.md`.

## Global palette (two-tone surfaces)

The application applies the theme to the global Qt palette (V1-style) so common
widgets automatically pick the correct surface colour:

- `QPalette.Window` (top-level backgrounds) derives from `theme.background_color`
- `QPalette.Base` / `QPalette.AlternateBase` (viewports like lists/trees/inputs)
  derive from slightly darker/lighter versions of `background_color`

In V2 this is done via `AppTheme.apply_to(QApplication)` (also exposed as
`datalens.ui.theme.palette.apply_palette(app, theme)`).

## Global QSS (app-wide styling)

On top of the Qt palette, V2 applies a small global stylesheet for consistent
UI chrome + inputs across the whole app (Welcome + Main windows, and plugin UI
that uses standard Qt widgets).

- QSS builder: `datalens.ui.theme.global_qss.build_global_qss`
- Applied via: `datalens.ui.theme.app_theme.AppTheme.apply_to`

Notable token:

- `ThemeSettings.background_secondary_color` drives menu/status chrome backgrounds
  (defaults to a derived colour from `background_color`).

## Color tokens

`ThemeSettings` stores the base palette (primary/secondary/tertiary/text and
semantic accents like confirm/cancel/warning). These are always treated as fully
opaque colors.

## Opacity policy

`ThemeOpacitySettings` standardises translucency for common states:

- Hover fills (typically a subtle tint of the selected/accent color)
- Selected/active "tinted" fills
- Subtle tracks/backgrounds
- Disabled text/surfaces/borders

If a plugin wants a different opacity, it can override it (either by passing an
explicit alpha to theme helpers, or by using custom QSS).

## Recommended plugin usage

### QSS-styled widgets (most plugin UI)

Use the theme-provided helper that returns Qt stylesheet-compatible `rgba(...)`
strings:

```python
bg = theme.selected_fill(theme.primary_color)      # default selected_fill alpha
border = theme.primary_color                       # full opacity
disabled = theme.disabled_fill_color(theme.background_color)
```

### Custom painting (QPainter)

Use `QColor` helpers:

```python
track = theme.qcolor_with_alpha(theme.background_color, theme.opacity.subtle_fill)
```

### Utility helpers (lighten/darken/contrast)

If you need simple colour math (for borders, pressed states, or dynamic text
contrast), use `datalens.ui.theme.color_utils`:

```python
from datalens.ui.theme.color_utils import contrast_text_color, lighten_hex
```

## "Selected card" pattern (V1-style)

To match the V1 preferences selection treatment:

- Selected background: `theme.selected_fill(theme.primary_color)` (tinted fill)
- Border: `theme.primary_color` (full opacity)
