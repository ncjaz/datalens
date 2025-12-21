# Minimal makefile for Sphinx documentation (DataLens V2)

SPHINXOPTS    ?= -c .
# Prefer module invocation so Windows venvs work even without sphinx-build on PATH.
SPHINXBUILD   ?= python -m sphinx
SPHINXPROJ    = datalens-v2
SOURCEDIR     = ..
BUILDDIR      = ../_build

.PHONY: help clean html html-pydata html-furo html-plugin livehtml
.PHONY: env-check

help:
	@$(SPHINXBUILD) -h

clean:
	@rm -rf "$(BUILDDIR)"

env-check:
	@python -c "import os, sys; print('Docs build environment:'); print(f'  sys.executable={sys.executable}'); print(f'  sys.prefix={sys.prefix}'); print(f'  CONDA_DEFAULT_ENV={os.getenv(\"CONDA_DEFAULT_ENV\")}'); print(f'  VIRTUAL_ENV={os.getenv(\"VIRTUAL_ENV\")}')"
	@python -c "import sys; \
isatty = getattr(sys.stdin, 'isatty', lambda: False)(); \
print(''); \
print('Press Enter to continue Sphinx build (Ctrl+C to abort)...' if isatty else 'Non-interactive stdin; skipping prompt.'); \
input() if isatty else None"

html:
	@$(MAKE) html-furo

html-pydata:
	@$(MAKE) env-check
	@SPHINX_THEME=pydata_sphinx_theme $(SPHINXBUILD) -b html $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html-pydata"

html-furo:
	@$(MAKE) env-check
	@SPHINX_THEME=furo $(SPHINXBUILD) -b html $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"

html-plugin:
	@$(MAKE) env-check
	@DATALENS_DOCS_INCLUDE_PLUGIN_DEV=1 SPHINX_THEME=furo $(SPHINXBUILD) -b html $(SPHINXOPTS) -D root_doc=sphinx/plugin_dev/index "$(SOURCEDIR)" "$(BUILDDIR)/html-plugin"

livehtml:
	@sphinx-autobuild $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"
