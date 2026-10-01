"""Small helpers for time intervals (ST-03).

An interval is a pair (start, end) of timezone-aware datetimes with start < end.
All intervals are HALF-OPEN: [start, end). The start belongs to the interval,
the end does not. So 10:00-11:00 and 11:00-12:00 touch but do not overlap,
and a room booked until 11:00 is free for a defense that starts at 11:00.

These functions never look at the clock and never change their inputs.
"""

from datetime import datetime

# One interval: (start, end), both timezone-aware, start < end.
TimeInterval = tuple[datetime, datetime]


def overlaps(a: TimeInterval, b: TimeInterval) -> bool:
    """True if the two intervals share at least one moment."""
    a_start, a_end = a
    b_start, b_end = b
    return a_start < b_end and b_start < a_end


def contains(outer: TimeInterval, inner: TimeInterval) -> bool:
    """True if every moment of `inner` is also in `outer`."""
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def merge(intervals: list[TimeInterval]) -> list[TimeInterval]:
    """Return the union as a sorted list of separate intervals.

    Overlapping or touching intervals are joined: [9-10) + [10-11) -> [9-11).
    Intervals with end <= start are ignored (they contain no moment).
    """
    valid = sorted(interval for interval in intervals if interval[0] < interval[1])
    merged: list[TimeInterval] = []
    for start, end in valid:
        if merged and start <= merged[-1][1]:
            # Starts before (or exactly when) the previous one ends: extend it.
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def subtract(intervals: list[TimeInterval], cuts: list[TimeInterval]) -> list[TimeInterval]:
    """Return the parts of `intervals` that are not inside any of `cuts`.

    Used for "Tuesday, except 14:00-16:00".
    """
    remaining = merge(intervals)
    for cut_start, cut_end in merge(cuts):
        pieces: list[TimeInterval] = []
        for start, end in remaining:
            if not overlaps((start, end), (cut_start, cut_end)):
                pieces.append((start, end))
                continue
            # Keep the piece before the cut and the piece after it, if any.
            if start < cut_start:
                pieces.append((start, cut_start))
            if cut_end < end:
                pieces.append((cut_end, end))
        remaining = pieces
    return remaining


def clip(intervals: list[TimeInterval], bounds: TimeInterval) -> list[TimeInterval]:
    """Return the parts of `intervals` that lie inside `bounds`."""
    low, high = bounds
    clipped = [(max(start, low), min(end, high)) for start, end in intervals]
    return merge(clipped)  # merge also drops pieces that became empty
