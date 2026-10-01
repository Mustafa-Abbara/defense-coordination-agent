"""Turning local wall-clock times into UTC (ST-03).

"Wall-clock time" is what a clock on the wall shows in one place, for example
"Tuesday 3 Nov, 10:00 in New York". It has no time zone attached yet.
To store it, we attach the place's IANA zone and convert it to UTC.

Twice a year this is tricky (daylight saving time, DST):
- In autumn one hour happens TWICE (Paris, 25 Oct 2026: 02:00-03:00 repeats).
- In spring one hour does NOT EXIST (clocks jump forward).
`zoneinfo` handles both. We always take the first reading (fold=0), and
`is_unclear_wall_time` tells the caller when a written time was one of these
special times, so it can be flagged instead of silently guessed (FM-15).
"""

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

from app.core.enums import Weekday

# Weekday enum in the same order as date.weekday(): Monday = 0 ... Sunday = 6.
WEEKDAYS_IN_ORDER: list[Weekday] = list(Weekday)


@cache
def zone(name: str) -> ZoneInfo:
    """Return the ZoneInfo for an IANA name. Names are checked by the models first."""
    return ZoneInfo(name)


def weekday_of(day: date) -> Weekday:
    return WEEKDAYS_IN_ORDER[day.weekday()]


def wall_time(day: date, offset: timedelta) -> datetime:
    """Local wall-clock time `offset` after midnight of `day` (no zone yet).

    Adding a timedelta to a datetime WITHOUT a zone is plain clock arithmetic:
    midnight + 25 h = 01:00 the next day, whatever DST does.
    """
    return datetime.combine(day, time(0)) + offset


def wall_to_utc(wall: datetime, zone_name: str) -> datetime:
    """Attach the zone to a wall-clock time and convert it to UTC.

    fold=0 (the default) means: if the time happens twice, take the first one;
    if it does not exist, use the offset from before the change.
    """
    return wall.replace(tzinfo=zone(zone_name)).astimezone(UTC)


def is_unclear_wall_time(wall: datetime, zone_name: str) -> bool:
    """True if `wall` happens twice (autumn) or never (spring) in that zone."""
    tz = zone(zone_name)
    first = wall.replace(tzinfo=tz, fold=0)
    second = wall.replace(tzinfo=tz, fold=1)
    happens_twice = first.utcoffset() != second.utcoffset()
    # A time that does not exist does not survive a round trip through UTC.
    round_trip = first.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    does_not_exist = round_trip != wall
    return happens_twice or does_not_exist


def day_start_utc(day: date, zone_name: str) -> datetime:
    """The UTC moment when `day` starts (local midnight) in that zone."""
    return wall_to_utc(wall_time(day, timedelta(0)), zone_name)


def local_date(moment: datetime, zone_name: str) -> date:
    """The calendar date of an aware UTC moment, as seen in that zone."""
    return moment.astimezone(zone(zone_name)).date()


def dates_between(first: date, last: date) -> list[date]:
    """Every date from `first` to `last`, both included."""
    count = (last - first).days + 1
    return [first + timedelta(days=i) for i in range(max(count, 0))]
