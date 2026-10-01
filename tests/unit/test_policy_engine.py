"""PolicyEngine: setup checks (FR-02), slot checks, notice deadline (ST-03).

The repository policy.yaml is used (Beirut, term 1 Sep - 20 Dec 2026, 14 days'
notice, MSc 90 min, PhD 120 min, MSc needs a mandatory ADVISOR and INTERNAL).
"""

from datetime import date, timedelta

import pytest
from builders import NOW, committee, defense, engine, member, utc
from pydantic import ValidationError

from app.core.config import policy_version
from app.core.enums import Role
from app.core.models import Slot
from app.services.policy_engine import DefenseSetup, PolicyEngine

ENGINE = engine()


def codes(violations: list) -> list[str]:
    return sorted(v.code.value for v in violations)


def setup(members: list | None = None, **defense_changes: object) -> DefenseSetup:
    return DefenseSetup(
        defense=defense(**defense_changes),
        members=committee() if members is None else members,
    )


# ---------------------------------------------------------------- the engine itself


def test_engine_reports_the_policy_and_its_version() -> None:
    assert ENGINE.current().notice_days == 14
    assert ENGINE.version() == policy_version(ENGINE.current())


# ---------------------------------------------------------------- validate_setup (FR-02)


def test_valid_setup_has_no_violations() -> None:
    assert ENGINE.validate_setup(setup(), NOW) == []


def test_missing_required_role_is_reported() -> None:
    members = [
        member("M1", Role.ADVISOR),
        member("M2", Role.CHAIR),
        member("M3", Role.EXTERNAL),
    ]
    assert codes(ENGINE.validate_setup(setup(members), NOW)) == ["REQUIRED_ROLE_MISSING"]


def test_required_role_held_only_by_an_optional_member_does_not_count() -> None:
    members = [
        member("M1", Role.ADVISOR),
        member("M2", Role.INTERNAL, is_mandatory=False),
        member("M3", Role.CHAIR),
    ]
    found = ENGINE.validate_setup(setup(members), NOW)
    assert codes(found) == ["REQUIRED_ROLE_MISSING"]
    assert "INTERNAL" in found[0].message


def test_phd_needs_more_roles_and_members() -> None:
    found = ENGINE.validate_setup(setup(degree_level="PHD"), NOW)
    # PhD: at least 5 members; needs CHAIR and EXTERNAL too.
    assert codes(found) == [
        "COMMITTEE_TOO_SMALL",
        "REQUIRED_ROLE_MISSING",
        "REQUIRED_ROLE_MISSING",
    ]


def test_more_than_seven_members_is_too_large() -> None:
    members = [member("M1", Role.ADVISOR)] + [
        member(f"M{i}", Role.INTERNAL, email=f"extra{i}@example.edu") for i in range(2, 8)
    ]
    extra = member("M7", Role.INTERNAL, id="m-8", email="eighth@example.edu")
    found = ENGINE.validate_setup(setup(members + [extra]), NOW)
    assert "COMMITTEE_TOO_LARGE" in codes(found)
    assert "DUPLICATE_ALIAS" in codes(found)


def test_duplicate_email_ignores_case_and_never_shows_the_address() -> None:
    members = committee()
    members[2] = member("M3", Role.INTERNAL, email="PERSON1@Example.EDU")
    found = ENGINE.validate_setup(setup(members), NOW)
    assert codes(found) == ["DUPLICATE_EMAIL"]
    assert found[0].field == "members.M3"
    assert "@" not in found[0].message  # privacy: aliases only


def test_member_from_another_defense_is_rejected() -> None:
    members = committee()
    members[1] = member("M2", Role.INTERNAL, defense_id="d-other")
    assert "MEMBER_OF_OTHER_DEFENSE" in codes(ENGINE.validate_setup(setup(members), NOW))


def test_remote_only_member_rules() -> None:
    members = committee() + [
        member("M4", Role.EXTERNAL, attendance="REMOTE_ONLY"),
        member("M5", Role.INTERNAL, attendance="REMOTE_ONLY", is_mandatory=False),
    ]
    found = codes(ENGINE.validate_setup(setup(members), NOW))
    # M5's role may not be remote, and 2 remote members > max 1.
    assert found == ["REMOTE_ROLE_NOT_ALLOWED", "TOO_MANY_REMOTE_MEMBERS"]


def test_remote_member_in_an_in_person_defense() -> None:
    members = committee() + [member("M4", Role.EXTERNAL, attendance="REMOTE_ONLY")]
    found = ENGINE.validate_setup(setup(members, attendance_mode="IN_PERSON"), NOW)
    assert codes(found) == ["REMOTE_MEMBER_IN_PERSON_DEFENSE"]
    assert found[0].field == "attendance_mode"


def test_window_outside_term() -> None:
    found = ENGINE.validate_setup(
        setup(window_start=date(2026, 12, 14), window_end=date(2026, 12, 23)), NOW
    )
    assert codes(found) == ["WINDOW_OUTSIDE_TERM"]


def test_window_must_leave_room_for_the_notice_period() -> None:
    # window_end - today must be at least 14 days (state_machine.md -> DRAFT).
    # Today = Sun 1 Nov; the window ends Sun 15 Nov: exactly 14 days, allowed.
    found = ENGINE.validate_setup(
        setup(window_start=date(2026, 11, 9), window_end=date(2026, 11, 15)), NOW
    )
    assert "WINDOW_TOO_SHORT_FOR_NOTICE" not in codes(found)
    one_day_late = NOW + timedelta(days=1)
    found = ENGINE.validate_setup(
        setup(window_start=date(2026, 11, 9), window_end=date(2026, 11, 15)), one_day_late
    )
    assert "WINDOW_TOO_SHORT_FOR_NOTICE" in codes(found)


def test_window_with_only_weekend_and_blackout_days() -> None:
    eng = engine(blackout_dates=[date(2026, 11, 16)])
    found = eng.validate_setup(
        setup(window_start=date(2026, 11, 14), window_end=date(2026, 11, 16)), NOW
    )
    assert codes(found) == ["NO_WORKING_DAY_IN_WINDOW"]


def test_many_problems_are_all_reported_at_once() -> None:
    members = [member("M1", Role.ADVISOR)]
    found = ENGINE.validate_setup(
        setup(members, window_start=date(2026, 12, 19), window_end=date(2026, 12, 21)),
        utc(2026, 12, 15),
    )
    assert codes(found) == [
        "COMMITTEE_TOO_SMALL",
        "NO_WORKING_DAY_IN_WINDOW",
        "REQUIRED_ROLE_MISSING",
        "WINDOW_OUTSIDE_TERM",
        "WINDOW_TOO_SHORT_FOR_NOTICE",
    ]


def test_setup_with_too_many_members_for_the_schema_is_rejected() -> None:
    # A hostile or broken client sending 50 members gets a validation error,
    # not a slow check.
    with pytest.raises(ValidationError):
        DefenseSetup(defense=defense(), members=[member("M1")] * 50)


# ---------------------------------------------------------------- check_slot


def slot(day: int, hour: int, minute: int = 0, minutes: int = 90) -> Slot:
    """A slot on `day` Nov 2026 starting at hour:minute Beirut time (UTC+2)."""
    start = utc(2026, 11, day, hour - 2, minute)
    return Slot(start=start, end=start + timedelta(minutes=minutes))


def test_good_slot_passes() -> None:
    assert ENGINE.check_slot(defense(), slot(17, 10), NOW) == []


@pytest.mark.parametrize(
    ("the_slot", "expected"),
    [
        (slot(17, 10, minutes=60), "WRONG_DURATION"),
        (slot(21, 10), "NOT_A_WORKING_DAY"),  # Saturday
        (slot(17, 7, 45), "OUTSIDE_WORKING_HOURS"),  # starts 07:45
        (slot(17, 16, 45), "OUTSIDE_WORKING_HOURS"),  # ends 18:15
        (slot(30, 10), "OUTSIDE_WINDOW"),  # Mon 30 Nov
    ],
)
def test_bad_slot_is_rejected_with_the_right_code(the_slot: Slot, expected: str) -> None:
    assert codes(ENGINE.check_slot(defense(), the_slot, NOW)) == [expected]


def test_slot_ending_exactly_at_closing_time_is_allowed() -> None:
    assert ENGINE.check_slot(defense(), slot(17, 16, 30), NOW) == []


def test_slot_over_midnight_is_outside_working_hours() -> None:
    late = Slot(start=utc(2026, 11, 17, 21), end=utc(2026, 11, 17, 22, 30))  # 23:00-00:30 local
    assert "OUTSIDE_WORKING_HOURS" in codes(ENGINE.check_slot(defense(), late, NOW))


def test_blackout_and_term() -> None:
    eng = engine(
        blackout_dates=[date(2026, 11, 18)],
        term_windows=[{"start": "2026-09-01", "end": "2026-11-20"}],
    )
    assert codes(eng.check_slot(defense(), slot(18, 10), NOW)) == ["BLACKOUT_DATE"]
    assert codes(eng.check_slot(defense(), slot(24, 10), NOW)) == ["OUTSIDE_TERM"]


def test_notice_deadline_and_its_boundary() -> None:
    the_slot = slot(17, 10)  # Tue 17 Nov 10:00 local = 08:00 UTC
    deadline = ENGINE.notice_deadline(the_slot)
    assert deadline == utc(2026, 11, 3, 8)  # 14 days earlier, same local time
    assert ENGINE.check_slot(defense(), the_slot, deadline) == []  # exactly at: still OK
    too_late = deadline + timedelta(minutes=1)
    assert codes(ENGINE.check_slot(defense(), the_slot, too_late)) == ["NOTICE_DEADLINE_PASSED"]


def test_engine_can_be_built_from_any_valid_policy() -> None:
    eng = PolicyEngine(engine(notice_days=0).current())
    assert eng.notice_deadline(slot(17, 10)) == slot(17, 10).start
