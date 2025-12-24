from __future__ import annotations

"""
Plugin dependency checking + optional installer (V1-style, removable)
====================================================================

V2 plugin discovery is metadata-only: it reads `manifest.json` and `requirements.txt`
without importing plugin runtime code.

This module provides:

- A lightweight requirement checker (based on installed distributions), so the UI
  can report "missing dependencies" before users enable a plugin.
- An optional "install requirements" helper that installs into the *current*
  Python environment (experimental, similar to V1 UX).

Notes
-----
- This is not a sandbox/security boundary.
- Installing into the running environment can be fragile (conda/pip mixing,
  version conflicts). Keep this feature isolated here so we can replace it with
  per-plugin venv / out-of-process plugins later.
"""

from dataclasses import dataclass
import os
import subprocess
import sys
import time
from typing import Iterable

from datalens.core.logging import get_logger
from datalens.infra.background.loader_context import LoaderCancelled, LoaderContext
from datalens.services.plugins.registry import PluginRecord

log = get_logger(__name__)


@dataclass(frozen=True)
class RequirementStatus:
    requirement: str
    status: str  # ok|missing|incompatible|skipped|unknown
    installed_version: str | None = None
    details: str | None = None


@dataclass(frozen=True)
class PluginDependencyReport:
    pip: tuple[RequirementStatus, ...]
    manual: tuple[str, ...]

    @property
    def missing_pip(self) -> tuple[str, ...]:
        return tuple(r.requirement for r in self.pip if r.status in {"missing", "incompatible"})

    @property
    def ok(self) -> bool:
        return not self.missing_pip


def _try_import_packaging():
    try:
        from packaging.requirements import Requirement  # type: ignore
        from packaging.specifiers import SpecifierSet  # noqa: F401
        from packaging.version import Version  # noqa: F401

        return Requirement
    except Exception:
        return None


def _try_importlib_metadata_version(dist_name: str) -> str | None:
    try:
        from importlib import metadata

        return metadata.version(dist_name)
    except Exception:
        return None


def _check_one(requirement_line: str) -> RequirementStatus:
    raw = str(requirement_line or "").strip()
    if not raw or raw.startswith("#"):
        return RequirementStatus(requirement=raw, status="skipped")

    Requirement = _try_import_packaging()
    if Requirement is None:
        return RequirementStatus(
            requirement=raw,
            status="unknown",
            details="packaging not installed; cannot parse/verify requirement specifiers",
        )

    try:
        req = Requirement(raw)
    except Exception as exc:
        return RequirementStatus(requirement=raw, status="unknown", details=f"Invalid requirement: {exc}")

    try:
        if req.marker is not None and not req.marker.evaluate():
            return RequirementStatus(requirement=raw, status="skipped", details="marker evaluates false")
    except Exception:
        return RequirementStatus(requirement=raw, status="unknown", details="failed to evaluate marker")

    installed = _try_importlib_metadata_version(req.name)
    if installed is None:
        return RequirementStatus(requirement=raw, status="missing")

    try:
        if req.specifier and installed not in req.specifier:
            return RequirementStatus(requirement=raw, status="incompatible", installed_version=installed)
    except Exception:
        return RequirementStatus(requirement=raw, status="unknown", installed_version=installed, details="specifier check failed")

    return RequirementStatus(requirement=raw, status="ok", installed_version=installed)


def check_plugin_dependencies(record: PluginRecord) -> PluginDependencyReport:
    """
    Return a dependency report for the plugin record.

    This uses the derived `requirements.txt` specifiers plus any manual
    requirements listed in the manifest.
    """
    pip_reqs = tuple(getattr(record.requirements, "pip_requirements", ()) or ())
    manual = tuple(getattr(record.definition, "manual_pip_requirements", ()) or ())
    return PluginDependencyReport(pip=tuple(_check_one(r) for r in pip_reqs), manual=manual)


def plugin_installer_enabled() -> bool:
    """
    Return True if the experimental plugin installer UI should be enabled.

    This is intentionally an env var so it is easy to disable/remove later.
    """
    raw = os.environ.get("DATALENS_ENABLE_PLUGIN_INSTALLER", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def install_pip_requirements(
    requirements: Iterable[str],
    *,
    ctx: LoaderContext | None = None,
    extra_pip_args: tuple[str, ...] = (),
) -> None:
    """
    Install pip requirements into the current Python environment.

    This is an optional V1-style convenience feature. It is intentionally kept
    in one module so we can remove/replace it later with per-plugin venvs.
    """
    reqs = [str(r).strip() for r in requirements if str(r).strip()]
    if not reqs:
        return

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        *extra_pip_args,
        *reqs,
    ]

    log.info(
        "Installing plugin requirements",
        extra={"operation": "plugin_install", "phase": "start", "count": len(reqs)},
    )
    if ctx is not None:
        ctx.log(f"Installing {len(reqs)} requirement(s)…")
        ctx.log("This installs into the current Python environment.")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        # Stream output in small chunks so cancel can be responsive.
        last_line_s = 0.0
        while True:
            if ctx is not None:
                ctx.raise_if_cancelled()

            line = proc.stdout.readline() if proc.stdout is not None else ""
            if line:
                now = time.time()
                # Avoid spamming; forward at most ~5 lines/sec to the loader UI.
                if ctx is not None and (now - last_line_s) >= 0.2:
                    ctx.log(line.rstrip())
                    last_line_s = now
                continue

            code = proc.poll()
            if code is not None:
                break
            time.sleep(0.05)
    except LoaderCancelled:
        try:
            if ctx is not None:
                ctx.log("Cancelling pip install…")
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        raise
    finally:
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass

    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed (exit code {proc.returncode}).")

    log.info("Plugin requirements installed", extra={"operation": "plugin_install", "phase": "end"})
