Plugin scaffolding templates

These files are copied into new plugin folders by `datalens.services.plugins.scaffold`.

Why templates-as-files?

- Easier to iterate: edit the generated output by editing real `.py` template files.
- Less code bloat: `scaffold.py` focuses on IO + validation, not huge multiline strings.

Placeholders

Templates use `${...}` placeholders (via `string.Template`).

- `${PLUGIN_ID}`: the plugin id (lowercase, stable)
- `${PLUGIN_NAME}`: display name
- `${PLUGIN_CLASS_NAME}`: generated Python class name for `plugin.py`

