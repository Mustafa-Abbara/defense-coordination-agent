"""DST cases around 25 Oct and 1 Nov 2026 (ST-03 acceptance #3, RK-T1, S29-S30).

The facts these tests rely on (checked with zoneinfo/tzdata 2026.4):
- Europe/Paris:      CEST (UTC+2) -> CET (UTC+1) on Sun 25 Oct 2026, 03:00 -> 02:00.
- America/New_York:  EDT (UTC-4)  -> EST (UTC-5) on Sun 1 Nov 2026, 02:00 -> 01:00.
- Asia/Beirut:       EEST (UTC+3) -> EET (UTC+2) on Sun 25 Oct 2026, 00:00 -> 23:00 (24 Oct).
So between 25 Oct and 1 Nov, Paris and New York are 5 hours apart instead of 6.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from builders import (
    defense,
    engine,
    free_room,
    member,
    solver_config,
    solver_input,
    statement,
    utc,
)

from app.core.enums import IssueCode, Role, StatementKind
from app.core.models import Slot
from app.services.date_resolver import DayRef, ResolverContext, TimeRef, resolve_statement
from app.services.local_time import is_unclear_wall_time, wall_time
from app.services.slot_solver import find_slots

POLICY = engine().current()


def resolve_one(zone_name: str, day: date, time_ref: TimeRef, **changes: Any) -> Any:
    values: dict[str, Any] = {
        "member_timezone": zone_name,
        "window_start": date(2026, 10, 19),
        "window_end": date(2026, 11, 13),
        "received_at": utc(2026, 10, 16, 9),
        "degree_level": "MSC",
    }
    values.update(changes)
    return resolve_statement(
        StatementKind.AVAILABLE,
        [DayRef(date=day)],
        [time_ref],
        [],
        ResolverContext.model_validate(values),
        POLICY,
    )


# ---------------------------------------------------------------- resolver


@pytest.mark.parametrize(
    ("zone_name", "day", "utc_hour"),
    [
        ("Europe/Paris", date(2026, 10, 23), 8),  # Fri before the change: UTC+2
        ("Europe/Paris", date(2026, 10, 26), 9),  # Mon after the change: UTC+1
        ("America/New_York", date(2026, 10, 30), 14),  # Fri before 1 Nov: UTC-4
        ("America/New_York", date(2026, 11, 2), 15),  # Mon after 1 Nov: UTC-5
        ("Asia/Beirut", date(2026, 10, 23), 7),  # UTC+3
        ("Asia/Beirut", date(2026, 10, 26), 8),  # UTC+2
    ],
)
def test_ten_am_local_is_the_right_utc_hour(zone_name: str, day: date, utc_hour: int) -> None:
    found = resolve_one(zone_name, day, TimeRef(start="10:00"))
    start = utc(day.year, day.month, day.day, utc_hour)
    assert found.intervals_utc == [(start, start + timedelta(minutes=90))]
    assert found.issues == []


def test_next_tuesday_written_before_us_change_lands_after_it() -> None:
    # S30: a New York member writes on Fri 30 Oct (EDT) "next Tuesday 10am my time".
    # Tue 3 Nov is after the change (EST), so 10:00 local = 15:00 UTC, not 14:00.
    found = resolve_statement(
        StatementKind.AVAILABLE,
        [DayRef(weekday="TUE", week="NEXT")],
        [TimeRef(start="10:00")],
        [],
        ResolverContext(
            member_timezone="America/New_York",
            window_start=date(2026, 10, 26),
            window_end=date(2026, 11, 13),
            received_at=utc(2026, 10, 30, 14),
            degree_level="MSC",
            time_zone_mentioned="my time",
        ),
        POLICY,
    )
    assert found.intervals_utc == [(utc(2026, 11, 3, 15), utc(2026, 11, 3, 16, 30))]
    assert found.issues == []


def test_mentioning_edt_after_the_us_change_is_flagged() -> None:
    # "10:00 EDT" for 3 Nov: New York is already on EST, so the mention is wrong.
    found = resolve_one(
        "America/New_York", date(2026, 11, 3), TimeRef(start="10:00"), time_zone_mentioned="EDT"
    )
    assert found.issues == [IssueCode.TZ_UNCLEAR]


@pytest.mark.parametrize(
    ("zone_name", "day", "clock"),
    [
        ("Europe/Paris", date(2026, 10, 25), "02:30"),  # happens twice
        ("America/New_York", date(2026, 11, 1), "01:30"),  # happens twice
        ("Asia/Beirut", date(2026, 10, 24), "23:30"),  # happens twice
    ],
)
def test_repeated_written_time_is_flagged_not_guessed(
    zone_name: str, day: date, clock: str
) -> None:
    found = resolve_one(zone_name, day, TimeRef(start=clock), window_start=date(2026, 10, 19))
    assert IssueCode.TZ_UNCLEAR in found.issues


def test_missing_local_time_in_spring_is_detected() -> None:
    # 29 Mar 2026, Paris: 02:00 -> 03:00, so 02:30 never happens.
    assert is_unclear_wall_time(wall_time(date(2026, 3, 29), timedelta(hours=2.5)), "Europe/Paris")
    assert not is_unclear_wall_time(
        wall_time(date(2026, 3, 29), timedelta(hours=4)), "Europe/Paris"
    )


def test_whole_day_on_change_day_has_25_hours() -> None:
    found = resolve_statement(
        StatementKind.UNAVAILABLE,
        [DayRef(date=date(2026, 10, 25))],
        [],
        [],
        ResolverContext(
            member_timezone="Europe/Paris",
            window_start=date(2026, 10, 19),
            window_end=date(2026, 11, 13),
            received_at=utc(2026, 10, 16),
            degree_level="MSC",
        ),
        POLICY,
    )
    [(start, end)] = found.intervals_utc
    assert end - start == timedelta(hours=25)
    assert found.issues == []  # midnight is not a time the member wrote


# ---------------------------------------------------------------- policy engine


def test_notice_deadline_keeps_local_wall_time_across_dst() -> None:
    # Defense Thu 5 Nov 10:00 Beirut (EET, 08:00 UTC). 14 days earlier is Thu 22 Oct,
    # when Beirut was on EEST (UTC+3): 10:00 local = 07:00 UTC, not 08:00.
    slot = Slot(start=utc(2026, 11, 5, 8), end=utc(2026, 11, 5, 9, 30))
    assert engine().notice_deadline(slot) == utc(2026, 10, 22, 7)


def test_working_hours_follow_the_local_clock_across_dst() -> None:
    eng = engine()
    window = defense(window_start=date(2026, 10, 19), window_end=date(2026, 10, 30))
    now = utc(2026, 9, 1)
    # 08:00 local is 05:00 UTC before 25 Oct and 06:00 UTC after.
    before = Slot(start=utc(2026, 10, 23, 5), end=utc(2026, 10, 23, 6, 30))
    after = Slot(start=utc(2026, 10, 26, 6), end=utc(2026, 10, 26, 7, 30))
    one_hour_early = Slot(start=utc(2026, 10, 26, 5), end=utc(2026, 10, 26, 6, 30))
    assert eng.check_slot(window, before, now) == []
    assert eng.check_slot(window, after, now) == []
    assert [v.code.value for v in eng.check_slot(window, one_hour_early, now)] == [
        "OUTSIDE_WORKING_HOURS"
    ]


# ---------------------------------------------------------------- solver


def test_solver_slots_shift_in_utc_but_not_in_local_time() -> None:
    everyone_free = [
        statement(m_id, "AVAILABLE", [(utc(2026, 10, 22), utc(2026, 10, 27))])
        for m_id in ("m-1", "m-2", "m-3")
    ]
    data = solver_input(
        defense=defense(window_start=date(2026, 10, 23), window_end=date(2026, 10, 26)),
        statements=everyone_free,
        now=utc(2026, 9, 1),
    )
    result = find_slots(data, engine(), solver_config())
    starts = {option.start for option in result.feasible}
    assert utc(2026, 10, 23, 5) in starts  # Fri 08:00 EEST
    assert utc(2026, 10, 26, 6) in starts  # Mon 08:00 EET
    assert utc(2026, 10, 26, 5) not in starts  # would be 07:00 local
    for option in result.feasible:
        assert option.end - option.start == timedelta(minutes=90)


def test_paris_and_new_york_members_meet_only_where_both_really_are_free() -> None:
    # Paris member free 15:00-18:00 local, New York member free 09:00-12:00 local,
    # on Mon 26 Oct (Paris already CET, New York still EDT: 5 h apart) and on
    # Mon 2 Nov (both on winter time: 6 h apart).
    # 26 Oct: Paris 14:00-17:00 UTC, NY 13:00-16:00 UTC -> overlap 14:00-16:00 UTC.
    # 2 Nov:  Paris 14:00-17:00 UTC, NY 14:00-17:00 UTC -> overlap 14:00-17:00 UTC,
    # but Beirut working hours end at 18:00 local = 16:00 UTC.
    paris = member("M1", Role.ADVISOR, timezone="Europe/Paris")
    new_york = member("M2", Role.EXTERNAL, timezone="America/New_York")
    statements = [
        statement("m-1", "AVAILABLE", [(utc(2026, 10, 26, 14), utc(2026, 10, 26, 17))]),
        statement("m-1", "AVAILABLE", [(utc(2026, 11, 2, 14), utc(2026, 11, 2, 17))]),
        statement("m-2", "AVAILABLE", [(utc(2026, 10, 26, 13), utc(2026, 10, 26, 16))]),
        statement("m-2", "AVAILABLE", [(utc(2026, 11, 2, 14), utc(2026, 11, 2, 17))]),
    ]
    data = solver_input(
        defense=defense(window_start=date(2026, 10, 26), window_end=date(2026, 11, 2)),
        members=[paris, new_york],
        statements=statements,
        rooms=[free_room()],
        now=utc(2026, 9, 1),
    )
    result = find_slots(data, engine(), solver_config())
    starts = sorted(option.start for option in result.feasible)
    assert starts[0] == utc(2026, 10, 26, 14)
    assert starts[-1] == utc(2026, 11, 2, 14, 30)  # ends 16:00 UTC = 18:00 Beirut
    for start in starts:
        assert start.date() in (date(2026, 10, 26), date(2026, 11, 2))
