"""Small factories for the ST-03 service tests.

Each function returns a valid object with sensible defaults; a test changes only
the fields it is about. All names and addresses are fake (synthetic data, R3 rule 9).

Default world (university zone Asia/Beirut, UTC+2 in November):
- MSc defense, window Mon 16 Nov - Fri 27 Nov 2026, audience 20, hybrid allowed;
- simulated "now" = Sun 1 Nov 2026 08:00 UTC (every slot in the window still
  meets the 14-day notice: the latest deadline is for 16 Nov 08:00 local -> 2 Nov).
"""

import itertools
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import PolicyConfig, SolverConfig, load_policy, load_solver
from app.core.enums import MemberStatus, Role, StatementKind
from app.core.models import AvailabilityStatement, CommitteeMember, Defense, Room
from app.services.policy_engine import PolicyEngine
from app.services.room_filter import RoomAvailability
from app.services.slot_solver import SolverInput

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

NOW = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
WINDOW_START = date(2026, 11, 16)
WINDOW_END = date(2026, 11, 27)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def policy(**changes: Any) -> PolicyConfig:
    """The repository policy.yaml, with some values changed."""
    base = load_policy(CONFIG_DIR / "policy.yaml").model_dump()
    base.update(changes)
    return PolicyConfig.model_validate(base)


def engine(**changes: Any) -> PolicyEngine:
    return PolicyEngine(policy(**changes))


def solver_config(**changes: Any) -> SolverConfig:
    base = load_solver(CONFIG_DIR / "solver.yaml").model_dump()
    base.update(changes)
    return SolverConfig.model_validate(base)


def defense(**changes: Any) -> Defense:
    values: dict[str, Any] = {
        "id": "d-1",
        "owner_user_id": "u-1",
        "title": "Synthetic Thesis Title",
        "degree_level": "MSC",
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "attendance_mode": "HYBRID_ALLOWED",
        "expected_audience": 20,
        "policy_version": "a" * 64,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return Defense.model_validate(values)


def member(alias: str, role: Role | str = Role.INTERNAL, **changes: Any) -> CommitteeMember:
    number = alias[1:]
    values: dict[str, Any] = {
        "id": f"m-{number}",
        "defense_id": "d-1",
        "alias": alias,
        "full_name": f"Synthetic Person{number}",
        "email": f"person{number}@example.edu",
        "role": role,
        "is_mandatory": True,
        "timezone": "Asia/Beirut",
        "attendance": "IN_PERSON",
        "status": MemberStatus.REPLIED,
    }
    values.update(changes)
    return CommitteeMember.model_validate(values)


def committee() -> list[CommitteeMember]:
    """A valid MSc committee: advisor + internal mandatory, one optional internal."""
    return [
        member("M1", Role.ADVISOR),
        member("M2", Role.INTERNAL),
        member("M3", Role.INTERNAL, is_mandatory=False),
    ]


_statement_ids = itertools.count(1)  # s-1, s-2, ... unique within a test run


def statement(
    member_id: str,
    kind: StatementKind | str,
    intervals: list[tuple[datetime, datetime]],
    **changes: Any,
) -> AvailabilityStatement:
    values: dict[str, Any] = {
        "id": f"s-{next(_statement_ids)}",
        "member_id": member_id,
        "source": "MANUAL",
        "kind": kind,
        "raw_expression": "{}",
        "intervals_utc": intervals,
        "confidence": 0.9,
        "observed_at": NOW,
        "extractor_version": "test",
    }
    values.update(changes)
    return AvailabilityStatement.model_validate(values)


def whole_window_available(member_id: str, **changes: Any) -> AvailabilityStatement:
    """'Any time in the window works' for one member (kind can be changed too)."""
    kind = changes.pop("kind", StatementKind.AVAILABLE)
    return statement(
        member_id,
        kind,
        [(utc(2026, 11, 15), utc(2026, 11, 28))],
        **changes,
    )


def room(room_id: str, capacity: int = 30, hybrid: bool = True, **changes: Any) -> Room:
    values = {
        "id": room_id,
        "name": f"Room {room_id}",
        "building": "Building B",
        "capacity": capacity,
        "hybrid_capable": hybrid,
    }
    values.update(changes)
    return Room.model_validate(values)


def free_room(room_id: str = "r-1", capacity: int = 30, hybrid: bool = True) -> RoomAvailability:
    return RoomAvailability(room=room(room_id, capacity, hybrid), busy=[])


def solver_input(**changes: Any) -> SolverInput:
    """Everyone mandatory is available the whole window; one free hybrid room."""
    members = changes.pop("members", committee())
    values: dict[str, Any] = {
        "defense": defense(),
        "members": members,
        "statements": [whole_window_available(m.id) for m in members],
        "rooms": [free_room()],
        "now": NOW,
    }
    values.update(changes)
    return SolverInput.model_validate(values)


def one_day(day: int) -> tuple[datetime, datetime]:
    """The whole local (Beirut, UTC+2) day `day` November 2026, in UTC."""
    start = utc(2026, 11, day) - timedelta(hours=2)
    return (start, start + timedelta(days=1))
