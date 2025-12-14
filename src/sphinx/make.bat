@ECHO OFF

REM Minimal make.bat for Sphinx documentation (DataLens V2)

REM Prefer module invocation so venv/conda builds work without sphinx-build on PATH.
where sphinx-build >NUL 2>NUL
IF %ERRORLEVEL%==0 (
  SET SPHINXBUILD=sphinx-build
) ELSE (
  SET SPHINXBUILD=python -m sphinx
)
SET SPHINXOPTS=-c .
SET SOURCEDIR=..
SET BUILDDIR=..\_build

IF "%1"=="" GOTO help

IF /I "%1"=="help" GOTO help
IF /I "%1"=="clean" GOTO clean
IF /I "%1"=="html" GOTO html_furo
IF /I "%1"=="html-furo" GOTO html_furo
IF /I "%1"=="html-pydata" GOTO html_pydata
IF /I "%1"=="html-plugin" GOTO html_plugin

ECHO Unknown target: %1
GOTO end

:help
ECHO Please use `make ^<target^>` where ^<target^> is one of:
ECHO   html         to build the docs with the default furo theme
ECHO   html-furo    to build the docs with the furo theme
ECHO   html-pydata  to build the docs with the pydata_sphinx_theme
ECHO   html-plugin  to build the plugin developer docs (subset)
ECHO   clean        to remove the built documentation
ECHO   help         to show this help message
GOTO end

:clean
RMDIR /S /Q "%BUILDDIR%" 2>NUL
GOTO end

:html_furo
SET SPHINX_THEME=furo
%SPHINXBUILD% -b html %SPHINXOPTS% "%SOURCEDIR%" "%BUILDDIR%\html"
GOTO end

:html_pydata
SET SPHINX_THEME=pydata_sphinx_theme
%SPHINXBUILD% -b html %SPHINXOPTS% "%SOURCEDIR%" "%BUILDDIR%\html-pydata"
GOTO end

:html_plugin
SET SPHINX_THEME=furo
%SPHINXBUILD% -b html %SPHINXOPTS% -D root_doc=sphinx/plugin_dev/index "%SOURCEDIR%" "%BUILDDIR%\html-plugin"
GOTO end

:end
