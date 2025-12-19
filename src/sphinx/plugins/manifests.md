# Plugin manifests

Plugins should declare their features declaratively so the runtime can present a
consistent enable/disable UX and validate compatibility.

V2 treats any folder that contains a `manifest.json` as a plugin root. The
loader discovers plugin roots recursively under:

- `datalens/plugins/` (shipped plugins, optionally grouped into packs)
- `<user data dir>/plugins/` (user-installed plugins, optionally grouped into packs)

Minimum manifest fields:

- `id`, `name`, `version`
- `stage` (one of `dev`, `alpha`, `beta`, `release`)
- optional `group` (e.g. `Data annotation`, `Models`)
- optional `core_version_constraint`
- list of feature entries (kind + entrypoint + display metadata)
- optional dependency declaration (see below)

As V2 grows, keep manifests stable and evolve via additive fields.

## Stage

`stage` is a UX hint so the welcome screen (and future plugin manager) can
highlight whether a plugin is experimental or stable.

Recommended values:

- `dev`: internal/unstable, may change frequently
- `alpha`: early preview
- `beta`: feature complete but still stabilising
- `release`: stable

If omitted, the runtime treats the stage as `release`.

## Grouping

Grouping is a UX hint so related plugins can be displayed together on the
welcome screen (and in any “workspace features” selector).

Example groups:

- **Data annotation**: Annotation + Review plugins
- **Models**: Train + Evaluation plugins

UI idea:

- Plugins in the same group can be rendered as adjacent cards with a shared
  outline and a small group header label.

## Dependencies (module checks + install)

V1 includes feature dependency checks and an installation workflow. V2 is
building toward the same, but today the story is intentionally simpler.

Recommended approach:

- Each plugin can ship a `requirements.txt` (or equivalent) in its plugin
  directory.
- The plugin loader reads that file for display/diagnostics (so we can show what
  a plugin depends on).
- **No automatic installation is performed yet**. Dependencies must already be
  installed in the active Python environment.
- Future: a plugin manager workflow can check whether those requirements are
  satisfied and offer a guided install experience.

Why derive from `requirements.txt`?

- Keeps dependencies next to the plugin code.
- Works for both shipped and external plugins.
- Avoids duplicating dependency lists in multiple places.

When not to use `requirements.txt`:

- For very small plugins with no optional deps, an empty `requirements.txt` is
  fine, and you can rely on `manual_pip_requirements` only when needed.
