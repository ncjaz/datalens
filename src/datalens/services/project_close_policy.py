from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectClosePolicy:
    """
    Centralized policy defaults for project close/flush behavior.

    Notes:
    - These values are used by UI orchestrators (loader stages / message boxes),
      not by low-level DB code.
    - Timeouts are "whole operation" budgets for safe closes. The underlying
      close routine apportions the remaining time across plugin flush hooks,
      DB flush, and IO flush.
    """

    safe_close_timeout_seconds: float = 30.0
    io_shutdown_timeout_seconds: float = 5.0


_DEFAULT = ProjectClosePolicy()


def default_project_close_policy() -> ProjectClosePolicy:
    """Return the default close policy for the app."""

    return _DEFAULT


__all__ = ["ProjectClosePolicy", "default_project_close_policy"]

