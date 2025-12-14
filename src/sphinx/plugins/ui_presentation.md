# Plugin UI presentation (welcome screen)

The plugin runtime exposes `PluginDefinition` metadata which the welcome screen
uses to render plugin cards and feature toggles.

## Metadata sources

- `PluginDefinition.name`, `description`, `version`, `author`, `homepage`
- `PluginDefinition.features` (tabs/services/datasources/models)
- `PluginDefinition.group` (optional)
- `PluginDefinition.manual_pip_requirements` (optional)

## Grouped plugins

If `group` is set, the welcome UI can render plugins in a grouped layout:

- Sort by `group` then plugin name.
- Render group header once.
- Render a shared outline around the contiguous cards.

If `group` is missing, the plugin is rendered as a standalone card.

## Dependencies

For plugins with a `requirements.txt` and/or `manual_pip_requirements`, show:

- availability status (installed / missing / incompatible)
- install button (runs the shared installer workflow)
- a short explanation of what will be installed

If `manual_pip_requirements` is non-empty, also show:

- a “manual install required” section with a link/instructions (e.g. PyTorch
  selector), since the correct wheel may be OS/CUDA-specific.
