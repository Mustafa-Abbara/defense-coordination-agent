"""RoomFilter: capacity, hybrid, buffer, order (ST-03, FR-14)."""

from datetime import timedelta

from builders import room, utc
from hypothesis import given
from hypothesis import strategies as st

from app.core.enums import AttendanceMode, MemberAttendance
from app.core.models import Slot
from app.services.intervals import overlaps
from app.services.room_filter import RoomAvailability, defense_needs_hybrid, fitting_rooms

SLOT = Slot(start=utc(2026, 11, 17, 8), end=utc(2026, 11, 17, 9, 30))


def available(room_id: str, capacity: int, hybrid: bool, busy: list | None = None):
    return RoomAvailability(room=room(room_id, capacity, hybrid), busy=busy or [])


def ids(rooms: list) -> list[str]:
    return [r.id for r in rooms]


def test_smallest_fitting_room_first_then_by_id() -> None:
    candidates = [
        available("r-big", 120, True),
        available("r-b", 30, True),
        available("r-a", 30, False),
        available("r-tiny", 10, True),  # too small
    ]
    found = fitting_rooms(candidates, SLOT, min_capacity=20, needs_hybrid=False, buffer_minutes=0)
    assert ids(found) == ["r-a", "r-b", "r-big"]


def test_hybrid_need_removes_non_hybrid_rooms() -> None:
    candidates = [available("r-a", 30, False), available("r-b", 40, True)]
    found = fitting_rooms(candidates, SLOT, min_capacity=20, needs_hybrid=True, buffer_minutes=0)
    assert ids(found) == ["r-b"]


def test_capacity_equal_to_audience_fits() -> None:
    found = fitting_rooms(
        [available("r-a", 20, True)], SLOT, min_capacity=20, needs_hybrid=False, buffer_minutes=0
    )
    assert ids(found) == ["r-a"]


def test_buffer_before_and_after_is_respected() -> None:
    # Busy until 07:50: free without a buffer, taken with a 15-minute buffer.
    ends_just_before = [(utc(2026, 11, 17, 7), utc(2026, 11, 17, 7, 50))]
    starts_just_after = [(utc(2026, 11, 17, 9, 40), utc(2026, 11, 17, 11))]
    for busy in (ends_just_before, starts_just_after):
        candidates = [available("r-a", 30, True, busy)]
        assert ids(fitting_rooms(candidates, SLOT, 20, False, buffer_minutes=0)) == ["r-a"]
        assert fitting_rooms(candidates, SLOT, 20, False, buffer_minutes=15) == []


def test_back_to_back_booking_is_free_when_buffer_is_zero() -> None:
    busy = [(utc(2026, 11, 17, 6), utc(2026, 11, 17, 8))]  # ends exactly at the slot start
    assert ids(fitting_rooms([available("r-a", 30, True, busy)], SLOT, 20, False, 0)) == ["r-a"]


def test_no_rooms_gives_an_empty_list() -> None:
    assert fitting_rooms([], SLOT, 20, False, 15) == []


def test_defense_needs_hybrid() -> None:
    assert defense_needs_hybrid(AttendanceMode.HYBRID_REQUIRED, [])
    assert defense_needs_hybrid(AttendanceMode.HYBRID_ALLOWED, [MemberAttendance.REMOTE_ONLY])
    assert not defense_needs_hybrid(AttendanceMode.HYBRID_ALLOWED, [MemberAttendance.REMOTE_OK])
    assert not defense_needs_hybrid(AttendanceMode.IN_PERSON, [MemberAttendance.IN_PERSON])


# ---------------------------------------------------------------- property

busy_block = st.tuples(st.integers(0, 20 * 60), st.integers(15, 240)).map(
    lambda pair: (
        utc(2026, 11, 17) + timedelta(minutes=pair[0]),
        utc(2026, 11, 17) + timedelta(minutes=pair[0] + pair[1]),
    )
)
room_entry = st.builds(
    lambda i, capacity, hybrid, busy: available(f"r-{i}", capacity, hybrid, busy),
    st.integers(0, 99),
    st.integers(1, 200),
    st.booleans(),
    st.lists(busy_block, max_size=3),
)


@given(
    candidates=st.lists(room_entry, max_size=8, unique_by=lambda c: c.room.id),
    min_capacity=st.integers(1, 150),
    needs_hybrid=st.booleans(),
    buffer_minutes=st.integers(0, 60),
)
def test_every_returned_room_really_fits(
    candidates: list[RoomAvailability], min_capacity: int, needs_hybrid: bool, buffer_minutes: int
) -> None:
    found = fitting_rooms(candidates, SLOT, min_capacity, needs_hybrid, buffer_minutes)
    buffer = timedelta(minutes=buffer_minutes)
    by_id = {c.room.id: c for c in candidates}
    for chosen in found:
        assert chosen.capacity >= min_capacity
        assert chosen.hybrid_capable or not needs_hybrid
        for busy in by_id[chosen.id].busy:
            assert not overlaps((SLOT.start - buffer, SLOT.end + buffer), busy)
    assert [(r.capacity, r.id) for r in found] == sorted((r.capacity, r.id) for r in found)
    # A big enough, hybrid, never-busy room is never left out.
    found_ids = {r.id for r in found}
    for c in candidates:
        if not c.busy and c.room.hybrid_capable and c.room.capacity >= min_capacity:
            assert c.room.id in found_ids
