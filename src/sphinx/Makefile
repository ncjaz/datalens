# Minimal makefile for Sphinx documentation (DataLens V2)

SPHINXOPTS    ?= -c .
# Prefer module invocation so Windows venvs work even without sphinx-build on PATH.
SPHINXBUILD   ?= python -m sphinx
SPHINXPROJ    = datalens-v2
SOURCEDIR     = ..
BUILDDIR      = ../_build

.PHONY: help clean html html-pydata html-furo html-plugin livehtml

help:
	@$(SPHINXBUILD) -h

clean:
	@rm -rf "$(BUILDDIR)"

html:
	@$(MAKE) html-furo

html-pydata:
	@SPHINX_THEME=pydata_sphinx_theme $(SPHINXBUILD) -b html $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html-pydata"

html-furo:
	@SPHINX_THEME=furo $(SPHINXBUILD) -b html $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"

html-plugin:
	@SPHINX_THEME=furo $(SPHINXBUILD) -b html $(SPHINXOPTS) -D root_doc=sphinx/plugin_dev/index "$(SOURCEDIR)" "$(BUILDDIR)/html-plugin"

livehtml:
	@sphinx-autobuild $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"
