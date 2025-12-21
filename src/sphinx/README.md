---
orphan: true
---

# V2 Sphinx configuration

Sphinx configuration and build helpers for the DataLens V2 documentation live in
this folder.

## Build

From `datalens/src/sphinx`:

- Install tooling: `python -m pip install -r requirements.txt`
- Build (Windows): `make.bat html`
- Build (POSIX): `make html`
- Build plugin docs only: `make.bat html-plugin` / `make html-plugin`

Output lands in `datalens/src/_build/html`.

## Mermaid diagrams

This Sphinx config enables `sphinxcontrib-mermaid` and treats fenced blocks like
` ```mermaid` as Mermaid directives, so Markdown diagrams render in HTML.
