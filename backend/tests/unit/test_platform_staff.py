"""Who may change which Duolink staff account (Milestone 17, ADR 0013)."""

import pytest

from app.domain.platform_staff import (
    SUPER_ADMIN,
    SUPPORT,
    StaffMember,
    StaffRuleError,
    check_staff_change,
)

ALICE = StaffMember(id=1, role=SUPER_ADMIN, is_active=True)
BOB = StaffMember(id=2, role=SUPER_ADMIN, is_active=True)
CARA = StaffMember(id=3, role=SUPPORT, is_active=True)
DORA = StaffMember(id=4, role=SUPPORT, is_active=False)


def test_a_super_admin_may_change_another_member_freely():
    # Two Super Admins (Alice, Bob): Alice demotes Bob, deactivates Cara, promotes Dora.
    check_staff_change(1, BOB, new_role=SUPPORT, new_active=True, active_super_admins=2)
    check_staff_change(1, CARA, new_role=SUPPORT, new_active=False, active_super_admins=2)
    check_staff_change(1, DORA, new_role=SUPER_ADMIN, new_active=True, active_super_admins=2)


def test_a_change_that_changes_nothing_is_always_allowed():
    # The only Super Admin saves her own profile with the same role and the same state.
    check_staff_change(1, ALICE, new_role=SUPER_ADMIN, new_active=True, active_super_admins=1)


@pytest.mark.parametrize(
    ("new_role", "new_active"), [(SUPPORT, True), (SUPER_ADMIN, False), (SUPPORT, False)]
)
def test_the_last_active_super_admin_cannot_be_demoted_or_deactivated(new_role, new_active):
    # One active Super Admin (Alice) and any way of taking her power away.
    with pytest.raises(StaffRuleError) as caught:
        check_staff_change(
            1, ALICE, new_role=new_role, new_active=new_active, active_super_admins=1
        )
    assert caught.value.code == "LAST_SUPER_ADMIN"


def test_the_last_super_admin_is_protected_from_anyone_not_only_herself():
    # Cara is the actor id here; the count is what protects Alice.
    with pytest.raises(StaffRuleError) as caught:
        check_staff_change(3, ALICE, new_role=SUPPORT, new_active=True, active_super_admins=1)
    assert caught.value.code == "LAST_SUPER_ADMIN"


@pytest.mark.parametrize(
    ("new_role", "new_active"), [(SUPPORT, True), (SUPER_ADMIN, False), (SUPPORT, False)]
)
def test_nobody_demotes_or_deactivates_themselves(new_role, new_active):
    # Alice with Bob also a Super Admin: she still may not lower her own access.
    with pytest.raises(StaffRuleError) as caught:
        check_staff_change(
            1, ALICE, new_role=new_role, new_active=new_active, active_super_admins=2
        )
    assert caught.value.code == "SELF_CHANGE"


def test_a_member_may_not_deactivate_themselves_even_when_not_a_super_admin():
    with pytest.raises(StaffRuleError) as caught:
        check_staff_change(3, CARA, new_role=SUPPORT, new_active=False, active_super_admins=2)
    assert caught.value.code == "SELF_CHANGE"


def test_an_inactive_super_admin_does_not_count_as_one_to_protect():
    # Alice (active) is the only active Super Admin; Eve is an inactive one. Deactivating
    # Eve again, or demoting her, takes no power from anyone.
    eve = StaffMember(id=5, role=SUPER_ADMIN, is_active=False)
    check_staff_change(1, eve, new_role=SUPPORT, new_active=False, active_super_admins=1)


def test_an_unknown_role_is_refused():
    with pytest.raises(ValueError, match="role"):
        check_staff_change(1, CARA, new_role="root", new_active=True, active_super_admins=2)
