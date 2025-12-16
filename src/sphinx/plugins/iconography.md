# Iconography guidelines

Consistent iconography keeps DataLens workspaces cohesive as new features and
plugins arrive. Follow the principles below when adding new icons so glyphs
blend with the existing theme and UI shape language.

## Visual language

- Icons derive colour from the active `AppTheme` and its opacity policy.
- Prefer theme helpers (`with_alpha_hex`, `qcolor_with_alpha`, etc.) over hard-coded RGB values.
- Avoid introducing new “random” accent colours; use primary/secondary/tertiary + semantic accents.

## Shapes and strokes

- Prefer rounded rectangles, circles, and soft outlines.
- Use layered translucent fills with subtle 1px borders rather than flat solid fills.
- Match existing stroke weights:
  - 2–3 px outlines for most glyphs
  - slightly thicker emphasis for active/selected states

## Creating new glyphs

1. Design at **56×56 px** first (good default for toolbar/tool icons).
2. Decide which parts use:
   - primary (action/energy)
   - secondary (surfaces)
   - tertiary (highlights)
3. Implement as a theme-aware painter that exports a `QIcon`.

## Where code should live

- Shared icons: `datalens/ui/widgets/icons/`
- Animated indicators: `datalens/ui/widgets/icons/animated/`
- Plugin-specific icons: keep them inside the plugin package (next to the widget that owns the control).

## Interaction states

When previewing an icon in the UI, confirm:

- Disabled state remains legible (use opacity shifts, not new hues).
- Hover/pressed states are visible but subtle.
- The icon maintains contrast on both secondary surfaces and viewport surfaces.

Related docs:

- `theming.md` (colors + opacity)
- `ui_presentation.md` (welcome screen presentation)

