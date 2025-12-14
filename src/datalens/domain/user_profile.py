from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserProfile:
    """
    Optional user identity details.

    This is intentionally lightweight and can be extended later (organisation,
    avatar, etc.). For now, the profile is optional and the app should not gate
    startup flows on completeness.
    """

    name: str = ""
    email: str = ""

    def normalized(self) -> "UserProfile":
        """Return a normalized copy (trimmed name, lowercased email)."""
        return UserProfile(
            name=str(self.name or "").strip(),
            email=str(self.email or "").strip().lower(),
        )

    def is_complete(self) -> bool:
        """
        Return True when the profile looks "complete" enough for future gating.

        This is deliberately conservative: it does not perform strict email
        validation; it only checks for a non-empty name and a basic '@' in the
        email field.
        """
        p = self.normalized()
        return bool(p.name) and ("@" in p.email)

