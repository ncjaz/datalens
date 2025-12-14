"""
Sphinx extension to improve autosummary documentation:

1. Shorten class/function names in HTML toctrees for readability
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def shorten_html_toctree(app: Any, exc: Any) -> None:
    """Hook called at the end of the HTML build to post-process toctree links."""
    if exc or app.builder.name != "html":
        return

    build_dir = Path(app.outdir)
    for html_file in build_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
            original_content = content

            pattern = r'<a[^>]*href="[^"]*generated/[^"]*"[^>]*>(datalens\.[^<]+\.[A-Z][^<]*)</a>'

            def shorten_name(match):
                full_text = match.group(1)
                short_name = full_text.split(".")[-1]
                href_part = match.group(0).split(">")[0] + ">"
                return f"{href_part}{short_name}</a>"

            content = re.sub(pattern, shorten_name, content)

            sidebar_pattern = (
                r'(<a[^>]*href="[^"]*api/generated/[^"]*"[^>]*>)(datalens\.[^<]+\.[A-Z][^<]*)(</a>)'
            )

            def shorten_sidebar(match):
                short_name = match.group(2).split(".")[-1]
                return f"{match.group(1)}{short_name}{match.group(3)}"

            content = re.sub(sidebar_pattern, shorten_sidebar, content)

            if content != original_content:
                html_file.write_text(content, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Warning: Could not process {html_file}: {exc}")


def setup(app: Any) -> dict:
    """Setup the extension."""
    app.connect("build-finished", shorten_html_toctree)
    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": False,
    }

