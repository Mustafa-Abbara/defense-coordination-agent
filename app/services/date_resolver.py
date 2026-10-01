"""DateResolver: what a reply SAYS -> exact UTC intervals and issue codes (ST-03).

The extractor LLM (ST-08) only reports what the text says ("Tuesday", "next
week", "afternoon", "10:00"). It never outputs a timestamp. This module decides
what those words MEAN, with plain code (FR-06, ADR-004):

    DayRef + TimeRef + the member's time zone + policy -> UTC intervals + issues

Rules (each one is tested in tests/unit/test_date_resolver.py):

- Days and clock times are read in the MEMBER's registered zone.
- The defense window is read in the UNIVERSITY zone (policy.timezone, A-21).
- "this/next week" is relative to the day the message arrived, in the member's zone.
  Weeks start on Monday.
- Never guess silently (FM-15). An unclear phrase gives intervals for EVERY
  possible meaning plus an issue code. The solver then refuses to treat a flagged
  "available" as firm, while a flagged "unavailable" still blocks (the safe side).
- Day with no clock time: "available Tuesday" = the member's working hours that
  day; "unavailable Tuesday" = the whole day (A-22).
- Everything outside the window is cut off. A day reference with no date left
  inside the window is flagged OUT_OF_WINDOW.
"""

import datetime as dt
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.core.config import PolicyConfig
from app.core.enums import DegreeLevel, IssueCode, PartOfDay, StatementKind, Weekday
from app.core.fields import IanaTimeZone, StrictModel, UtcDatetime
from app.core.models import Interval
from app.services import intervals as iv
from app.services.local_time import (
    dates_between,
    day_start_utc,
    is_unclear_wall_time,
    local_date,
    wall_time,
    wall_to_utc,
    weekday_of,
    zone,
)

# ---------------------------------------------------------------- input schemas (interfaces.md)

# A real clock time "HH:MM" from 00:00 to 23:59. (interfaces.md only asked for
# two digits, colon, two digits; "25:99" would have passed that.)
ClockText = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]

WeekRef = Literal["THIS", "NEXT", "ANY_IN_WINDOW", "SPECIFIC"]
PartOfDayRef = Literal["MORNING", "AFTERNOON", "EVENING", "ALL_DAY"]


class DayRef(StrictModel):
    """Which day(s) a statement is about, exactly as the text says it."""

    # The field is called "date", so the type is written dt.date to avoid a name clash.
    date: dt.date | None = None  # an explicit date written in the email
    weekday: Weekday | None = None
    week: WeekRef | None = None
    week_of: dt.date | None = None  # only when week == "SPECIFIC"


class TimeRef(StrictModel):
    """Which time of day, as written. The resolver applies the time zone."""

    part_of_day: PartOfDayRef | None = None
    start: ClockText | None = None
    end: ClockText | None = None


class ResolverContext(StrictModel):
    """Facts the resolver needs besides the statement itself."""

    member_timezone: IanaTimeZone  # the member's registered zone
    window_start: dt.date  # the defense window, in the university zone
    window_end: dt.date
    received_at: UtcDatetime  # when the reply arrived; "this/next week" count from here
    degree_level: DegreeLevel  # "10:00" alone means a defense starting at 10:00
    time_zone_mentioned: str | None = Field(default=None, max_length=64)  # e.g. "CET"

    @model_validator(mode="after")
    def _window_in_order(self) -> Self:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        return self


class Resolution(StrictModel):
    """The resolver's answer."""

    intervals_utc: list[Interval]  # sorted, merged, inside the window
    issues: list[IssueCode]  # sorted, no repeats
    dates: list[dt.date]  # member-local dates the statement refers to (inside the window)


# ---------------------------------------------------------------- main function

# Kinds that state availability and therefore need at least one day.
_AVAILABILITY_KINDS = {
    StatementKind.AVAILABLE,
    StatementKind.UNAVAILABLE,
    StatementKind.CONDITIONAL,
}
# For these kinds, a day without a clock time means the whole day (the safe side).
_WHOLE_DAY_KINDS = {StatementKind.UNAVAILABLE, StatementKind.DECLINE}

_ONE_DAY = dt.timedelta(days=1)

# Local wall-clock range inside one day, as offsets from local midnight.
# (start, end) with end up to 24 h, or more when "10:00 + duration" passes midnight.
_LocalRange = tuple[dt.timedelta, dt.timedelta]


def resolve_statement(
    kind: StatementKind,
    days: list[DayRef],
    times: list[TimeRef],
    except_times: list[TimeRef],
    context: ResolverContext,
    policy: PolicyConfig,
) -> Resolution:
    """Turn one extracted statement into UTC intervals and issue codes."""
    issues: set[IssueCode] = set()

    if not days:
        # "Mornings work" with no day at all. The extractor must use
        # week="ANY_IN_WINDOW" for "every day", so a missing day is unclear.
        if kind in _AVAILABILITY_KINDS:
            issues.add(IssueCode.AMBIGUOUS_DAY)
        return Resolution(intervals_utc=[], issues=sorted(issues), dates=[])

    all_dates: set[dt.date] = set()
    for day_ref in days:
        dates, day_issues = _dates_for(day_ref, context, policy)
        issues |= day_issues
        inside = [day for day in dates if context.window_start <= day <= context.window_end]
        if not inside and IssueCode.UNPARSEABLE not in day_issues:
            issues.add(IssueCode.OUT_OF_WINDOW)
        all_dates.update(inside)

    ranges, time_issues = _ranges_for(kind, times, policy, context.degree_level)
    cut_ranges, cut_issues = _ranges_for(
        StatementKind.UNAVAILABLE, except_times, policy, context.degree_level
    )
    issues |= time_issues | cut_issues

    found: list[Interval] = []
    for day in sorted(all_dates):
        day_intervals = _to_utc_intervals(day, ranges, context.member_timezone)
        cuts = _to_utc_intervals(day, cut_ranges, context.member_timezone) if except_times else []
        found.extend(iv.subtract(day_intervals, cuts))
        if _has_unclear_written_time(day, times + except_times, context.member_timezone):
            issues.add(IssueCode.TZ_UNCLEAR)

    if not _zone_mention_matches(context, sorted(all_dates)):
        issues.add(IssueCode.TZ_UNCLEAR)

    window = _window_utc(context, policy)
    return Resolution(
        intervals_utc=iv.clip(found, window),
        issues=sorted(issues),
        dates=sorted(all_dates),
    )


# ---------------------------------------------------------------- days


def _dates_for(
    day_ref: DayRef, context: ResolverContext, policy: PolicyConfig
) -> tuple[list[dt.date], set[IssueCode]]:
    """All dates one DayRef can mean (member-local), and any issue found."""
    if day_ref.date is not None:
        return _explicit_date(day_ref.date, day_ref.weekday)

    # A week reference must come with week_of exactly when it is SPECIFIC.
    if (day_ref.week == "SPECIFIC") != (day_ref.week_of is not None):
        return [], {IssueCode.UNPARSEABLE}

    window_dates = dates_between(context.window_start, context.window_end)
    working_days = set(policy.working_hours.weekdays)

    if day_ref.week is None:
        if day_ref.weekday is None:
            return [], {IssueCode.UNPARSEABLE}  # nothing to go on
        # "Tuesday" with no week: fine if the window has one Tuesday, unclear if more.
        matches = [day for day in window_dates if weekday_of(day) == day_ref.weekday]
        if len(matches) > 1:
            return matches, {IssueCode.AMBIGUOUS_WEEK}
        return matches, set()

    if day_ref.week == "ANY_IN_WINDOW":
        # "Tuesdays work" -> every Tuesday; "any day works" -> every working day.
        wanted = {day_ref.weekday} if day_ref.weekday else working_days
        return [day for day in window_dates if weekday_of(day) in wanted], set()

    # THIS, NEXT, or SPECIFIC: one calendar week (Monday to Sunday).
    received = local_date(context.received_at, context.member_timezone)
    if day_ref.week_of is not None:  # SPECIFIC (checked above)
        anchor = day_ref.week_of
    elif day_ref.week == "NEXT":
        anchor = received + 7 * _ONE_DAY
    else:  # THIS
        anchor = received
    monday = anchor - anchor.weekday() * _ONE_DAY
    week_dates = [monday + i * _ONE_DAY for i in range(7)]

    if day_ref.weekday is None:
        return [day for day in week_dates if weekday_of(day) in working_days], set()

    day = week_dates[list(Weekday).index(day_ref.weekday)]
    if day_ref.week == "THIS" and day < received:
        # "this Monday", written on a Wednesday: last Monday, or the coming one?
        return [day, day + 7 * _ONE_DAY], {IssueCode.AMBIGUOUS_DAY}
    if day_ref.week == "NEXT" and day - 7 * _ONE_DAY > received:
        # "next Friday", written on a Wednesday: in 2 days, or in 9 days?
        return [day - 7 * _ONE_DAY, day], {IssueCode.AMBIGUOUS_DAY}
    return [day], set()


def _explicit_date(
    written: dt.date, weekday: Weekday | None
) -> tuple[list[dt.date], set[IssueCode]]:
    """A written date. If a weekday is written too, they must agree."""
    if weekday is None or weekday_of(written) == weekday:
        return [written], set()
    # "Tuesday 18 Nov" when 18 Nov is a Wednesday. Keep both meanings: the date
    # as written, and the named weekday in the same week (FM-15).
    monday = written - written.weekday() * _ONE_DAY
    named_day = monday + list(Weekday).index(weekday) * _ONE_DAY
    return sorted([written, named_day]), {IssueCode.WEEKDAY_DATE_MISMATCH}


# ---------------------------------------------------------------- times of day


def _ranges_for(
    kind: StatementKind, times: list[TimeRef], policy: PolicyConfig, degree: DegreeLevel
) -> tuple[list[_LocalRange], set[IssueCode]]:
    """Local wall-clock ranges for one day, from the TimeRefs."""
    default = _default_range(kind, policy)
    if not times:
        return [default], set()

    ranges: list[_LocalRange] = []
    issues: set[IssueCode] = set()
    duration = dt.timedelta(minutes=policy.duration_minutes[degree])
    for time_ref in times:
        start = _offset(time_ref.start)
        end = _offset(time_ref.end)
        if start is not None and end is not None:
            if end <= start:
                issues.add(IssueCode.UNPARSEABLE)  # "from 16:00 to 14:00"
                continue
            ranges.append((start, end))
        elif start is not None:
            # "10:00 works": a defense starting at 10:00, so 10:00 + its duration.
            ranges.append((start, start + duration))
        elif end is not None:
            # "until 15:00": from the start of the default range.
            if end <= default[0]:
                issues.add(IssueCode.UNPARSEABLE)
                continue
            ranges.append((default[0], end))
        elif time_ref.part_of_day in (None, "ALL_DAY"):
            ranges.append(default)
        else:
            part = policy.part_of_day[PartOfDay(time_ref.part_of_day)]
            if part is None:
                # EVENING is null in policy.yaml: outside working hours.
                issues.add(IssueCode.OUT_OF_WINDOW)
                continue
            ranges.append((_clock_offset(part[0]), _clock_offset(part[1])))
    return ranges, issues


def _default_range(kind: StatementKind, policy: PolicyConfig) -> _LocalRange:
    """The range used when a statement names a day but no time (A-22)."""
    if kind in _WHOLE_DAY_KINDS:
        return (dt.timedelta(0), _ONE_DAY)
    hours = policy.working_hours
    return (_clock_offset(hours.start), _clock_offset(hours.end))


def _offset(clock_text: str | None) -> dt.timedelta | None:
    if clock_text is None:
        return None
    hours, minutes = clock_text.split(":")
    return dt.timedelta(hours=int(hours), minutes=int(minutes))


def _clock_offset(clock: dt.time) -> dt.timedelta:
    return dt.timedelta(hours=clock.hour, minutes=clock.minute)


def _to_utc_intervals(day: dt.date, ranges: list[_LocalRange], zone_name: str) -> list[Interval]:
    """Place local ranges on one date and convert them to UTC (DST-safe)."""
    found: list[Interval] = []
    for start, end in ranges:
        start_utc = wall_to_utc(wall_time(day, start), zone_name)
        end_utc = wall_to_utc(wall_time(day, end), zone_name)
        if start_utc < end_utc:  # can be equal only inside a spring-forward gap
            found.append((start_utc, end_utc))
    return found


def _has_unclear_written_time(day: dt.date, times: list[TimeRef], zone_name: str) -> bool:
    """True if a clock time the member WROTE happens twice or never on that day.

    Midnight and policy ranges are not checked: only times a person wrote can be
    misunderstood, so only those are flagged.
    """
    for time_ref in times:
        for text in (time_ref.start, time_ref.end):
            offset = _offset(text)
            if offset is not None and is_unclear_wall_time(wall_time(day, offset), zone_name):
                return True
    return False


# ---------------------------------------------------------------- time zone mentioned


# Phrases that simply mean "my own zone".
_OWN_ZONE_PHRASES = {"MY TIME", "LOCAL", "LOCAL TIME", "MY LOCAL TIME"}
# Generic names that cover both the winter and the summer abbreviation.
_GENERIC_ZONE_NAMES = {
    "ET": {"EST", "EDT"},
    "CT": {"CST", "CDT"},
    "MT": {"MST", "MDT"},
    "PT": {"PST", "PDT"},
}


def _zone_mention_matches(context: ResolverContext, dates: list[dt.date]) -> bool:
    """True if a mentioned zone ("CET", "my time") agrees with the registered zone.

    The mention is never trusted on its own. If it does not match, the registered
    zone is still used and the statement is flagged TZ_UNCLEAR (FM-15, S32).
    """
    mentioned = context.time_zone_mentioned
    if mentioned is None:
        return True
    text = " ".join(mentioned.upper().split())  # trim and squeeze spaces
    if not text or text in _OWN_ZONE_PHRASES:
        return True
    if text == context.member_timezone.upper():
        return True

    # Compare with the abbreviation the zone really uses on those dates (EST vs EDT).
    tz = zone(context.member_timezone)
    check_dates = dates or [local_date(context.received_at, context.member_timezone)]
    for day in check_dates:
        noon = dt.datetime.combine(day, dt.time(12), tzinfo=tz)
        actual = noon.tzname() or ""
        allowed = {actual}
        for generic, members in _GENERIC_ZONE_NAMES.items():
            if actual in members:
                allowed.add(generic)
        if text not in allowed:
            return False
    return True


# ---------------------------------------------------------------- window


def _window_utc(context: ResolverContext, policy: PolicyConfig) -> Interval:
    """The defense window as one UTC interval (window dates are university-local)."""
    start = day_start_utc(context.window_start, policy.timezone)
    end = day_start_utc(context.window_end + _ONE_DAY, policy.timezone)
    return (start, end)
