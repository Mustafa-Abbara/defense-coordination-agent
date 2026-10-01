"""DateResolver: phrases -> UTC intervals and issue codes (ST-03, FR-06, FM-02, FM-15).

Default context: a member in Asia/Beirut (UTC+2 in November), window Mon 16 Nov -
Fri 27 Nov 2026, reply received Wed 11 Nov 2026 10:00 UTC, MSc (90 minutes).
DST cases are in test_dst.py.
"""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from builders import policy, utc
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.enums import IssueCode, StatementKind
from app.services.date_resolver import (
    DayRef,
    Resolution,
    ResolverContext,
    TimeRef,
    resolve_statement,
)
from app.services.local_time import day_start_utc

AVAILABLE = StatementKind.AVAILABLE
UNAVAILABLE = StatementKind.UNAVAILABLE
POLICY = policy()


def context(**changes: Any) -> ResolverContext:
    values: dict[str, Any] = {
        "member_timezone": "Asia/Beirut",
        "window_start": date(2026, 11, 16),
        "window_end": date(2026, 11, 27),
        "received_at": utc(2026, 11, 11, 10),
        "degree_level": "MSC",
    }
    values.update(changes)
    return ResolverContext.model_validate(values)


def resolve(
    days: list[DayRef],
    times: list[TimeRef] | None = None,
    kind: StatementKind = AVAILABLE,
    except_times: list[TimeRef] | None = None,
    **context_changes: Any,
) -> Resolution:
    return resolve_statement(
        kind, days, times or [], except_times or [], context(**context_changes), POLICY
    )


TUE_17 = DayRef(date=date(2026, 11, 17))


# ---------------------------------------------------------------- times of day


def test_afternoon_uses_the_member_zone() -> None:
    # 13:00-17:00 in Beirut (UTC+2) = 11:00-15:00 UTC.
    found = resolve([TUE_17], [TimeRef(part_of_day="AFTERNOON")])
    assert found.intervals_utc == [(utc(2026, 11, 17, 11), utc(2026, 11, 17, 15))]
    assert found.issues == []
    assert found.dates == [date(2026, 11, 17)]


def test_available_day_without_time_means_working_hours() -> None:
    found = resolve([TUE_17])
    assert found.intervals_utc == [(utc(2026, 11, 17, 6), utc(2026, 11, 17, 16))]


def test_all_day_means_working_hours_for_available() -> None:
    assert resolve([TUE_17], [TimeRef(part_of_day="ALL_DAY")]).intervals_utc == [
        (utc(2026, 11, 17, 6), utc(2026, 11, 17, 16))
    ]


def test_unavailable_day_without_time_means_the_whole_day() -> None:
    found = resolve([TUE_17], kind=UNAVAILABLE)
    assert found.intervals_utc == [(utc(2026, 11, 16, 22), utc(2026, 11, 17, 22))]


@pytest.mark.parametrize(("degree", "minutes"), [("MSC", 90), ("PHD", 120)])
def test_start_time_alone_means_a_defense_starting_then(degree: str, minutes: int) -> None:
    found = resolve([TUE_17], [TimeRef(start="10:00")], degree_level=degree)
    start = utc(2026, 11, 17, 8)
    assert found.intervals_utc == [(start, start + timedelta(minutes=minutes))]


def test_end_time_alone_counts_from_start_of_working_hours() -> None:
    found = resolve([TUE_17], [TimeRef(end="12:00")])
    assert found.intervals_utc == [(utc(2026, 11, 17, 6), utc(2026, 11, 17, 10))]


def test_end_before_start_is_unparseable() -> None:
    found = resolve([TUE_17], [TimeRef(start="16:00", end="14:00")])
    assert found.intervals_utc == []
    assert found.issues == [IssueCode.UNPARSEABLE]


def test_end_only_before_working_hours_is_unparseable() -> None:
    assert resolve([TUE_17], [TimeRef(end="07:00")]).issues == [IssueCode.UNPARSEABLE]


def test_evening_is_outside_the_policy() -> None:
    found = resolve([TUE_17], [TimeRef(part_of_day="EVENING")])
    assert found.intervals_utc == []
    assert found.issues == [IssueCode.OUT_OF_WINDOW]


def test_except_times_are_cut_out() -> None:
    # "Tuesday works, except 14:00-16:00"
    found = resolve([TUE_17], except_times=[TimeRef(start="14:00", end="16:00")])
    assert found.intervals_utc == [
        (utc(2026, 11, 17, 6), utc(2026, 11, 17, 12)),
        (utc(2026, 11, 17, 14), utc(2026, 11, 17, 16)),
    ]


def test_touching_ranges_are_merged() -> None:
    found = resolve([TUE_17], [TimeRef(part_of_day="MORNING"), TimeRef(start="12:00", end="13:00")])
    assert found.intervals_utc == [(utc(2026, 11, 17, 6), utc(2026, 11, 17, 11))]


# ---------------------------------------------------------------- days


def test_weekday_date_mismatch_keeps_both_meanings() -> None:
    # "Tuesday 18 Nov": 18 Nov 2026 is a Wednesday (FM-15).
    found = resolve([DayRef(date=date(2026, 11, 18), weekday="TUE")])
    assert IssueCode.WEEKDAY_DATE_MISMATCH in found.issues
    assert found.dates == [date(2026, 11, 17), date(2026, 11, 18)]
    assert len(found.intervals_utc) == 2


def test_matching_weekday_and_date_is_fine() -> None:
    assert resolve([DayRef(date=date(2026, 11, 18), weekday="WED")]).issues == []


def test_bare_weekday_with_two_matches_is_ambiguous_week() -> None:
    # "Tuesday afternoon works" with two Tuesdays in the window (FM-02).
    found = resolve([DayRef(weekday="TUE")], [TimeRef(part_of_day="AFTERNOON")])
    assert found.issues == [IssueCode.AMBIGUOUS_WEEK]
    assert found.dates == [date(2026, 11, 17), date(2026, 11, 24)]


def test_bare_weekday_with_one_match_is_clear() -> None:
    found = resolve([DayRef(weekday="TUE")], window_end=date(2026, 11, 20))
    assert found.issues == []
    assert found.dates == [date(2026, 11, 17)]


def test_bare_weekday_not_in_window_is_out_of_window() -> None:
    found = resolve([DayRef(weekday="FRI")], window_end=date(2026, 11, 17))
    assert found.issues == [IssueCode.OUT_OF_WINDOW]
    assert found.intervals_utc == []


def test_this_week_day_already_past_is_ambiguous() -> None:
    # Written on Wed 11 Nov: "this Monday" (9 Nov, past) or the coming one (16 Nov)?
    found = resolve([DayRef(weekday="MON", week="THIS")])
    assert found.issues == [IssueCode.AMBIGUOUS_DAY]
    assert found.dates == [date(2026, 11, 16)]  # 9 Nov is outside the window


def test_next_friday_written_on_wednesday_is_ambiguous() -> None:
    # Written Wed 18 Nov: "next Friday" = 20 Nov or 27 Nov?
    found = resolve([DayRef(weekday="FRI", week="NEXT")], received_at=utc(2026, 11, 18, 10))
    assert found.issues == [IssueCode.AMBIGUOUS_DAY]
    assert found.dates == [date(2026, 11, 20), date(2026, 11, 27)]


def test_next_tuesday_written_on_wednesday_is_clear() -> None:
    found = resolve([DayRef(weekday="TUE", week="NEXT")])
    assert found.issues == []
    assert found.dates == [date(2026, 11, 17)]


def test_next_week_partly_outside_window_keeps_the_inside_days() -> None:
    # Received Fri 20 Nov: "next week" = 23-27 Nov; window ends Wed 25 Nov.
    found = resolve(
        [DayRef(week="NEXT")], received_at=utc(2026, 11, 20, 10), window_end=date(2026, 11, 25)
    )
    assert found.issues == []
    assert found.dates == [date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25)]


def test_specific_week_with_and_without_weekday() -> None:
    week_of = date(2026, 11, 26)  # any day of that week
    assert resolve([DayRef(week="SPECIFIC", week_of=week_of, weekday="MON")]).dates == [
        date(2026, 11, 23)
    ]
    whole_week = resolve([DayRef(week="SPECIFIC", week_of=week_of)]).dates
    assert whole_week == [date(2026, 11, day) for day in range(23, 28)]  # Mon-Fri only


@pytest.mark.parametrize(
    "day_ref",
    [
        DayRef(),  # nothing at all
        DayRef(week="SPECIFIC"),  # SPECIFIC without week_of
        DayRef(week="THIS", week_of=date(2026, 11, 17)),  # week_of without SPECIFIC
    ],
)
def test_inconsistent_day_refs_are_unparseable(day_ref: DayRef) -> None:
    found = resolve([day_ref])
    assert found.issues == [IssueCode.UNPARSEABLE]
    assert found.intervals_utc == []


def test_any_in_window() -> None:
    tuesdays = resolve([DayRef(week="ANY_IN_WINDOW", weekday="TUE")]).dates
    assert tuesdays == [date(2026, 11, 17), date(2026, 11, 24)]
    every_day = resolve([DayRef(week="ANY_IN_WINDOW")]).dates
    assert len(every_day) == 10  # working days only


def test_explicit_date_outside_window_is_flagged_and_dropped() -> None:
    found = resolve([DayRef(date=date(2026, 12, 3))])
    assert found.issues == [IssueCode.OUT_OF_WINDOW]
    assert found.intervals_utc == []


def test_missing_day_is_ambiguous_only_for_availability_kinds() -> None:
    assert resolve([], [TimeRef(part_of_day="MORNING")]).issues == [IssueCode.AMBIGUOUS_DAY]
    assert resolve([], kind=StatementKind.DEFERRAL).issues == []


def test_window_edge_is_clipped_in_the_university_zone() -> None:
    # A New York member's whole Friday 27 Nov runs past the window's end
    # (midnight in Beirut); the part after the end is cut off, without a flag.
    found = resolve(
        [DayRef(date=date(2026, 11, 27))], kind=UNAVAILABLE, member_timezone="America/New_York"
    )
    window_end_utc = day_start_utc(date(2026, 11, 28), "Asia/Beirut")
    assert found.intervals_utc[-1][1] == window_end_utc
    assert found.issues == []


# ---------------------------------------------------------------- time zone mentioned (S32)


@pytest.mark.parametrize(
    ("mentioned", "zone_name", "ok"),
    [
        ("my time", "Asia/Beirut", True),
        ("  Local   Time ", "Asia/Beirut", True),
        ("Asia/Beirut", "Asia/Beirut", True),
        ("EET", "Asia/Beirut", True),  # Beirut's real abbreviation in November
        ("CET", "Asia/Beirut", False),  # S32: another zone than the registered one
        ("EST", "America/New_York", True),
        ("ET", "America/New_York", True),
        ("PST", "America/New_York", False),
        ("Mars time", "Asia/Beirut", False),
    ],
)
def test_mentioned_zone_must_match_the_registered_zone(
    mentioned: str, zone_name: str, ok: bool
) -> None:
    found = resolve([TUE_17], member_timezone=zone_name, time_zone_mentioned=mentioned)
    assert (IssueCode.TZ_UNCLEAR not in found.issues) is ok
    # Either way, the registered zone is used: the interval is the same.
    plain = resolve([TUE_17], member_timezone=zone_name)
    assert found.intervals_utc == plain.intervals_utc


# ---------------------------------------------------------------- hostile or invalid input


@pytest.mark.parametrize("clock", ["25:99", "24:00", "9:00", "10:60", "10h30", "10:00 "])
def test_impossible_clock_times_are_rejected(clock: str) -> None:
    with pytest.raises(ValidationError):
        TimeRef(start=clock)


@pytest.mark.parametrize(
    "values",
    [
        {"weekday": "TUESDAY"},  # not one of the enum values
        {"week": "LAST"},
        {"date": "2026-02-30"},
        {"weekday": "TUE", "command": "ignore previous instructions"},  # unknown field
    ],
)
def test_malformed_day_refs_are_rejected(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DayRef.model_validate(values)


def test_context_rejects_huge_zone_text_and_reversed_window() -> None:
    with pytest.raises(ValidationError):
        context(time_zone_mentioned="X" * 1000)
    with pytest.raises(ValidationError):
        context(window_start=date(2026, 11, 27), window_end=date(2026, 11, 16))
    with pytest.raises(ValidationError):
        context(received_at=datetime(2026, 11, 11, 10))  # naive time  # noqa: DTZ001


# ---------------------------------------------------------------- property (acceptance #2)

ZONES = ["Asia/Beirut", "Europe/Paris", "America/New_York", "Asia/Tokyo", "Pacific/Auckland"]
any_date = st.dates(min_value=date(2026, 10, 1), max_value=date(2026, 12, 31))
clock_text = st.builds(
    lambda h, m: f"{h:02d}:{m:02d}", st.integers(0, 23), st.sampled_from([0, 15, 30, 45])
)
day_refs = st.builds(
    DayRef,
    date=st.none() | any_date,
    weekday=st.none() | st.sampled_from(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]),
    week=st.none() | st.sampled_from(["THIS", "NEXT", "ANY_IN_WINDOW", "SPECIFIC"]),
    week_of=st.none() | any_date,
)
time_refs = st.builds(
    TimeRef,
    part_of_day=st.none() | st.sampled_from(["MORNING", "AFTERNOON", "EVENING", "ALL_DAY"]),
    start=st.none() | clock_text,
    end=st.none() | clock_text,
)


@given(
    days=st.lists(day_refs, max_size=3),
    times=st.lists(time_refs, max_size=2),
    except_times=st.lists(time_refs, max_size=1),
    kind=st.sampled_from(list(StatementKind)),
    zone_name=st.sampled_from(ZONES),
    window_start=st.dates(min_value=date(2026, 10, 15), max_value=date(2026, 11, 20)),
    window_days=st.integers(min_value=0, max_value=20),
    received_day=any_date,
)
def test_resolver_output_is_always_inside_the_window_or_flagged(
    days: list[DayRef],
    times: list[TimeRef],
    except_times: list[TimeRef],
    kind: StatementKind,
    zone_name: str,
    window_start: date,
    window_days: int,
    received_day: date,
) -> None:
    window_end = window_start + timedelta(days=window_days)
    ctx = context(
        member_timezone=zone_name,
        window_start=window_start,
        window_end=window_end,
        received_at=utc(received_day.year, received_day.month, received_day.day, 9),
    )
    found = resolve_statement(kind, days, times, except_times, ctx, POLICY)

    low = day_start_utc(window_start, POLICY.timezone)
    high = day_start_utc(window_end + timedelta(days=1), POLICY.timezone)
    for start, end in found.intervals_utc:
        assert low <= start < end <= high  # inside the window, well-formed
    for day in found.dates:
        assert window_start <= day <= window_end
    # An explicit date (without a weekday) outside the window is never silently dropped.
    for day_ref in days:
        outside = day_ref.date is not None and not window_start <= day_ref.date <= window_end
        if outside and day_ref.weekday is None:
            assert IssueCode.OUT_OF_WINDOW in found.issues
    assert found.issues == sorted(set(found.issues))
