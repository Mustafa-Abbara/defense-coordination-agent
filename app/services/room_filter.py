"""RoomFilter: which rooms fit a slot, smallest first (ST-03, FR-14).

A room fits when:
1. its capacity is at least the expected audience (A-23: the audience number
   counts everyone in the room, committee included);
2. it is hybrid-capable, if the defense needs hybrid;
3. it is free for the slot PLUS the setup buffer before and after
   (policy.buffer_minutes), so back-to-back bookings leave time to set up.

Sorting: smallest fitting capacity first (do not block a big hall for a small
defense), then by room id, so the order is the same on every run.

The busy times come from the RoomService (mock in ST-05). This module only
decides; it never books anything and never calls a service.
"""

from datetime import timedelta

from pydantic import Field

from app.core.enums import AttendanceMode, MemberAttendance
from app.core.fields import StrictModel
from app.core.models import Interval, Room, Slot
from app.services.intervals import overlaps


class RoomAvailability(StrictModel):
    """One room and the times it is already taken."""

    room: Room
    busy: list[Interval] = Field(default_factory=list)


def fitting_rooms(
    candidates: list[RoomAvailability],
    slot: Slot,
    min_capacity: int,
    needs_hybrid: bool,
    buffer_minutes: int,
) -> list[Room]:
    """Rooms that fit the slot, smallest capacity first, then by id."""
    buffer = timedelta(minutes=buffer_minutes)
    needed = (slot.start - buffer, slot.end + buffer)
    fitting = [
        candidate.room
        for candidate in candidates
        if candidate.room.capacity >= min_capacity
        and (candidate.room.hybrid_capable or not needs_hybrid)
        and not any(overlaps(needed, busy) for busy in candidate.busy)
    ]
    return sorted(fitting, key=lambda room: (room.capacity, room.id))


def defense_needs_hybrid(
    attendance_mode: AttendanceMode, attendances: list[MemberAttendance]
) -> bool:
    """True if the setup alone already needs a hybrid room.

    The solver adds slot-specific needs on top (a member's "only if hybrid").
    """
    if attendance_mode is AttendanceMode.HYBRID_REQUIRED:
        return True
    return MemberAttendance.REMOTE_ONLY in attendances
