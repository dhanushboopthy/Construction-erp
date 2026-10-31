"""Rules for Duolink's own staff accounts (Milestone 17, ADR 0013).

Two roles: a Super Admin can change things, Support only reads and answers tickets. Two guards
keep the platform from locking itself out: nobody lowers their own access, and the last active
Super Admin always stays one. Pure rules: the caller reads the counts and acts on the verdict.
"""

from dataclasses import dataclass

SUPER_ADMIN = "super_admin"
SUPPORT = "support"
ROLES = frozenset({SUPER_ADMIN, SUPPORT})


class StaffRuleError(ValueError):
    """A staff change that is not allowed. `code` is the API error code (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StaffMember:
    id: int
    role: str
    is_active: bool


def check_staff_change(
    actor_id: int,
    target: StaffMember,
    *,
    new_role: str,
    new_active: bool,
    active_super_admins: int,
) -> None:
    """Raise StaffRuleError unless `actor_id` may give `target` this role and state.

    `active_super_admins` counts active Super Admins before the change.
    """
    if new_role not in ROLES:
        raise ValueError(f"Unknown role {new_role!r}")
    loses_super_admin = (
        target.role == SUPER_ADMIN
        and target.is_active
        and (new_role != SUPER_ADMIN or not new_active)
    )
    if loses_super_admin and active_super_admins <= 1:
        raise StaffRuleError(
            "LAST_SUPER_ADMIN",
            "Duolink needs at least one active Super Admin. Make someone else a Super Admin first.",
        )
    lowers_own_access = new_role != target.role or (target.is_active and not new_active)
    if actor_id == target.id and lowers_own_access:
        raise StaffRuleError(
            "SELF_CHANGE", "You cannot change your own role or deactivate yourself."
        )
