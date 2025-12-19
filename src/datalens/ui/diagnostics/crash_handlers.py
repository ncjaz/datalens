from __future__ import annotations

"""
Crash/traceback handlers for developer visibility.

This module centralizes "last resort" crash logging so the QApplication wrapper
doesn't become a dumping ground for cross-cutting diagnostics concerns.

Design goals:
- Always emit *some* traceback information (even for thread crashes).
- Prefer a persistent log file under the user data directory when possible.
- Keep the installation idempotent (safe to call multiple times).
"""

from pathlib import Path
import faulthandler
import sys
import threading

from datalens.core.logging import get_logger
from datalens.infra.paths import datalens_user_data_dir


_installed = False
_installed_path: Path | None = None
_file_handle = None


def install_crash_handlers(*, crash_log_path: Path | None = None) -> Path | None:
    """
    Install crash handlers (best-effort).

    Installs:
    - `faulthandler` (all threads)
    - `sys.excepthook`
    - `threading.excepthook` (Python 3.8+)

    Returns:
        Path | None: the crash log path used for faulthandler output (if any).
    """
    global _installed, _installed_path, _file_handle
    if _installed:
        return _installed_path

    crash_log = get_logger("datalens.crash")

    _installed = True

    try:
        if crash_log_path is None:
            crash_log_path = datalens_user_data_dir() / "crash_tracebacks.log"
        crash_log_path = Path(crash_log_path)
        crash_log_path.parent.mkdir(parents=True, exist_ok=True)
        _installed_path = crash_log_path
        _file_handle = open(crash_log_path, "a", encoding="utf-8")
        faulthandler.enable(file=_file_handle, all_threads=True)
    except Exception:
        _installed_path = None
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

    def sys_hook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        crash_log.error(
            "Unhandled exception",
            exc_info=(exc_type, exc, tb),
            extra={"operation": "unhandled", "phase": "sys_excepthook"},
        )

    def thread_hook(args) -> None:  # type: ignore[no-untyped-def]
        crash_log.error(
            "Unhandled thread exception (thread=%s)",
            getattr(getattr(args, "thread", None), "name", "<unknown>"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            extra={"operation": "unhandled", "phase": "thread_excepthook"},
        )

    sys.excepthook = sys_hook
    try:
        threading.excepthook = thread_hook  # type: ignore[assignment]
    except Exception:
        pass

    return _installed_path


__all__ = ["install_crash_handlers"]

