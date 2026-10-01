"""Interval helpers: half-open [start, end) behavior (ST-03)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.services.intervals import clip, contains, merge, overlaps, subtract


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 17, hour, minute, tzinfo=UTC)


def test_touching_intervals_do_not_overlap() -> None:
    # 10-11 and 11-12 share no moment: the end is not part of an interval.
    assert not overlaps((at(10), at(11)), (at(11), at(12)))
    assert overlaps((at(10), at(11, 1)), (at(11), at(12)))


def test_contains_needs_the_whole_inner_interval() -> None:
    assert contains((at(9), at(12)), (at(9), at(12)))
    assert not contains((at(9), at(12)), (at(11), at(12, 15)))


def test_merge_joins_overlapping_and_touching_and_drops_empty() -> None:
    found = merge([(at(11), at(12)), (at(9), at(10)), (at(10), at(11)), (at(14), at(14))])
    assert found == [(at(9), at(12))]


def test_subtract_cuts_a_hole() -> None:
    # "Tuesday 9-17, except 14-16"
    assert subtract([(at(9), at(17))], [(at(14), at(16))]) == [
        (at(9), at(14)),
        (at(16), at(17)),
    ]


def test_subtract_and_clip_edges() -> None:
    assert subtract([(at(9), at(10))], [(at(8), at(11))]) == []
    assert subtract([(at(9), at(10))], [(at(10), at(11))]) == [(at(9), at(10))]
    assert clip([(at(8), at(12)), (at(13), at(14))], (at(9), at(13, 30))) == [
        (at(9), at(12)),
        (at(13), at(13, 30)),
    ]


# ---------------------------------------------------------------- property

minutes = st.integers(min_value=0, max_value=24 * 60)
raw_intervals = st.lists(st.tuples(minutes, minutes), max_size=8)


def to_times(pairs: list[tuple[int, int]]) -> list[tuple[datetime, datetime]]:
    base = datetime(2026, 11, 17, tzinfo=UTC)
    return [(base + timedelta(minutes=a), base + timedelta(minutes=b)) for a, b in pairs]


def covered(intervals: list[tuple[datetime, datetime]], moment: datetime) -> bool:
    return any(start <= moment < end for start, end in intervals)


@given(raw_intervals, raw_intervals)
def test_merge_and_subtract_keep_exactly_the_right_moments(
    pairs: list[tuple[int, int]], cut_pairs: list[tuple[int, int]]
) -> None:
    intervals, cuts = to_times(pairs), to_times(cut_pairs)
    merged = merge(intervals)
    rest = subtract(intervals, cuts)
    # merge: sorted, separate, non-empty.
    for (a_start, a_end), (b_start, _) in zip(merged, merged[1:], strict=False):
        assert a_start < a_end < b_start
    # Check every minute of the day.
    base = datetime(2026, 11, 17, tzinfo=UTC)
    for minute in range(0, 24 * 60 + 1, 5):
        moment = base + timedelta(minutes=minute)
        assert covered(merged, moment) == covered(intervals, moment)
        assert covered(rest, moment) == (covered(intervals, moment) and not covered(cuts, moment))
