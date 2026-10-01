"""SlotSolver: which slots are feasible now, and which are near-misses (ST-03, FR-12).

Plain code, no LLM (ADR-004). The agent can only pick from what this returns.

How it works, step by step:

1. Candidate slots: every working day in the defense window, every start time on
   a 15-minute grid (solver.yaml), from the start of working hours until the
   defense still ends inside them. All in the university zone (A-21).
2. Policy: PolicyEngine.check_slot removes slots that break a hard rule
   (notice, term, blackout, ...). Each removal is counted by reason.
3. Members: for each MANDATORY member, decide "available" or "blocked, because ...":
   - an ACTIVE unavailable/decline statement overlapping the slot blocks it,
     whatever its confidence (a wrong "no" only costs a slot; a wrong "yes" could
     cost a bad booking);
   - an ACTIVE available/conditional/confirm statement must CONTAIN the whole slot
     in one of its intervals, have confidence >= the threshold, and have no open
     issue. Otherwise the member is UNCLEAR for that slot;
   - stale statements still count but are listed in low_confidence_inputs.
4. Conditions: "only if hybrid" and "remote only" are checked against the policy
   (remote roles, max remote members) and make the slot need a hybrid room.
   Conditions code cannot check (IF_MEMBER_PRESENT, OTHER) block with CONDITION.
5. Rooms: RoomFilter must find at least one room, else the slot is blocked by ROOM.
6. Result: 0 blockers -> feasible; exactly 1 blocker -> near-miss; more -> removed.

Optional members never block a slot and never change the room need; they only
raise the score when they are available.
"""

import hashlib
from datetime import datetime, timedelta

from pydantic import Field

from app.core.config import PolicyConfig, SolverConfig
from app.core.enums import (
    AttendanceMode,
    BlockReason,
    MemberAttendance,
    MemberStatus,
    StatementCondition,
    StatementKind,
    StatementStatus,
)
from app.core.fields import MemberAlias, StrictModel, UtcDatetime
from app.core.models import AvailabilityStatement, CommitteeMember, Defense, Slot
from app.services.intervals import contains, overlaps
from app.services.local_time import dates_between, wall_time, wall_to_utc, weekday_of
from app.services.policy_engine import PolicyEngine
from app.services.room_filter import RoomAvailability, defense_needs_hybrid, fitting_rooms

# The "member" name used in NearMiss.blocked_by when the rooms are the problem.
ROOM_BLOCKER = "ROOM"

# Score weights. Each level is worth more than everything below it can add up to,
# so the score sorts by: 1) more optional members, 2) fewer stale inputs, 3) earlier.
_OPTIONAL_MEMBER_POINTS = 100.0  # at most 6 optional members -> 600
_STALE_INPUT_PENALTY = 10.0  # at most 7 stale inputs -> 70 (< 100)
# Earliness adds between 0 and 1 (< 10).

_POSITIVE_KINDS = {StatementKind.AVAILABLE, StatementKind.CONDITIONAL, StatementKind.CONFIRM}
_NEGATIVE_KINDS = {StatementKind.UNAVAILABLE, StatementKind.DECLINE}
# Conditions the solver can check by itself.
_CHECKABLE_CONDITIONS = {None, StatementCondition.HYBRID_REQUIRED, StatementCondition.REMOTE_ONLY}


# ---------------------------------------------------------------- input and output


class SolverInput(StrictModel):
    """Everything the solver looks at. Built from stored state (ST-04)."""

    defense: Defense
    members: list[CommitteeMember]
    statements: list[AvailabilityStatement]
    rooms: list[RoomAvailability]
    now: UtcDatetime  # simulated clock time
    # T02 option: treat members who have not replied (AWAITING_REPLY) as available.
    # Slots that need this are marked hypothetical and cannot be proposed (T07).
    what_if_pending_available: bool = False


class SlotOption(StrictModel):
    """A feasible slot (interfaces.md T02)."""

    slot_id: str
    start: UtcDatetime
    end: UtcDatetime
    score: float
    available: list[MemberAlias]  # mandatory and optional members available
    optional_missing: list[MemberAlias]
    conditions: list[str]  # for example "M5: HYBRID_REQUIRED"
    rooms_free: int = Field(ge=1)
    notice_deadline: UtcDatetime
    low_confidence_inputs: list[MemberAlias]  # stale statements used for this slot
    hypothetical: bool


class NearMiss(StrictModel):
    """A slot that fails for exactly one reason: one member, or the rooms."""

    slot_id: str
    start: UtcDatetime
    end: UtcDatetime
    blocked_by: list[tuple[str, BlockReason]]  # (alias or "ROOM", reason)


class SolverResult(StrictModel):
    feasible: list[SlotOption]  # best score first
    near_misses: list[NearMiss]  # earliest first
    infeasible_summary: dict[str, int]  # reason code -> number of slots it removed


# ---------------------------------------------------------------- one member, one slot


class _MemberCheck(StrictModel):
    """Internal: the verdict for one member on one slot."""

    blocked_by: BlockReason | None = None
    condition: StatementCondition | None = None
    stale: bool = False
    hypothetical: bool = False


def _effective_condition(statement: AvailabilityStatement) -> StatementCondition | None:
    # A CONDITIONAL statement without a condition is a condition we cannot check.
    if statement.kind is StatementKind.CONDITIONAL and statement.condition is None:
        return StatementCondition.OTHER
    return statement.condition


def _check_member(
    member: CommitteeMember,
    statements: list[AvailabilityStatement],
    slot: Slot,
    data: SolverInput,
    config: SolverConfig,
) -> _MemberCheck:
    """Can this member attend this slot, according to what they told us?"""
    slot_interval = (slot.start, slot.end)
    active = [s for s in statements if s.status is StatementStatus.ACTIVE]

    if member.status is MemberStatus.WITHDRAWN or any(
        s.kind is StatementKind.WITHDRAWAL for s in active
    ):
        return _MemberCheck(blocked_by=BlockReason.UNAVAILABLE)

    negatives = [s for s in active if s.kind in _NEGATIVE_KINDS]
    for statement in negatives:
        if any(overlaps(interval, slot_interval) for interval in statement.intervals_utc):
            return _MemberCheck(blocked_by=BlockReason.UNAVAILABLE)

    positives = [s for s in active if s.kind in _POSITIVE_KINDS]
    covering = [s for s in positives if any(contains(i, slot_interval) for i in s.intervals_utc)]
    firm = [s for s in covering if s.confidence >= config.confidence_threshold and not s.issues]
    usable = [s for s in firm if _effective_condition(s) in _CHECKABLE_CONDITIONS]
    stale_before = data.now - timedelta(days=config.staleness_days)

    if usable:
        # Prefer a statement without a condition, then a fresh one; id breaks ties.
        def preference(s: AvailabilityStatement) -> tuple[bool, bool, str]:
            return (_effective_condition(s) is not None, s.observed_at < stale_before, s.id)

        best = min(usable, key=preference)
        return _MemberCheck(
            condition=_effective_condition(best), stale=best.observed_at < stale_before
        )
    if firm:
        return _MemberCheck(blocked_by=BlockReason.CONDITION)  # only unverifiable conditions
    if covering:
        return _MemberCheck(blocked_by=BlockReason.UNCLEAR)
    if not positives and not negatives:
        if data.what_if_pending_available and member.status is MemberStatus.AWAITING_REPLY:
            return _MemberCheck(hypothetical=True)
        return _MemberCheck(blocked_by=BlockReason.NO_REPLY)
    return _MemberCheck(blocked_by=BlockReason.NOT_STATED)


# ---------------------------------------------------------------- one slot


class _SlotVerdict(StrictModel):
    """Internal: everything decided about one candidate slot."""

    blockers: list[tuple[str, BlockReason]]
    available: list[MemberAlias]
    optional_available: int
    optional_missing: list[MemberAlias]
    conditions: list[str]
    stale: list[MemberAlias]
    hypothetical: bool
    rooms_free: int


def _remote_place_ok(member: CommitteeMember, policy: PolicyConfig, remote_count: int) -> bool:
    """May this member attend remotely? Their role must allow it, and a place must be left.

    Members who are remote-only from the setup were counted already (and the setup
    check made sure they fit the limit), so they never need a new place.
    """
    if member.role not in policy.remote_allowed_roles:
        return False
    already_counted = member.attendance is MemberAttendance.REMOTE_ONLY
    return already_counted or remote_count < policy.max_remote_members


def _evaluate_slot(
    slot: Slot,
    data: SolverInput,
    engine: PolicyEngine,
    config: SolverConfig,
    by_member: dict[str, list[AvailabilityStatement]],
) -> _SlotVerdict:
    policy = engine.current()
    defense = data.defense
    members = sorted(data.members, key=lambda m: m.alias)
    in_person_only = defense.attendance_mode is AttendanceMode.IN_PERSON

    needs_hybrid = defense_needs_hybrid(defense.attendance_mode, [m.attendance for m in members])
    # Remote-only members from the setup already use remote places (checked in setup).
    remote_count = sum(1 for m in members if m.attendance is MemberAttendance.REMOTE_ONLY)

    blockers: list[tuple[str, BlockReason]] = []
    available: list[MemberAlias] = []
    optional_missing: list[MemberAlias] = []
    conditions: list[str] = []
    stale: list[MemberAlias] = []
    hypothetical = False

    # Mandatory members first: they decide the room need and the remote places.
    for member in [m for m in members if m.is_mandatory]:
        check = _check_member(member, by_member.get(member.id, []), slot, data, config)
        reason = check.blocked_by
        if reason is None and check.condition is not None:
            if in_person_only:
                reason = BlockReason.CONDITION  # hybrid or remote is not possible at all
            elif check.condition is StatementCondition.REMOTE_ONLY:
                if not _remote_place_ok(member, policy, remote_count):
                    reason = BlockReason.CONDITION  # role not allowed, or no place left
                elif member.attendance is not MemberAttendance.REMOTE_ONLY:
                    remote_count += 1  # a new remote member uses a place
        if reason is not None:
            blockers.append((member.alias, reason))
            continue
        available.append(member.alias)
        if check.condition is not None:
            needs_hybrid = True
            conditions.append(f"{member.alias}: {check.condition.value}")
        if check.stale:
            stale.append(member.alias)
        hypothetical = hypothetical or check.hypothetical

    # Optional members: counted only if they fit the slot as it already is.
    optional_available = 0
    for member in [m for m in members if not m.is_mandatory]:
        check = _check_member(member, by_member.get(member.id, []), slot, data, config)
        fits = check.blocked_by is None and not check.hypothetical
        if fits and check.condition is not None:
            # The condition must already be met: optional members never change the room.
            fits = needs_hybrid and not in_person_only
            if fits and check.condition is StatementCondition.REMOTE_ONLY:
                fits = _remote_place_ok(member, policy, remote_count)
                if fits and member.attendance is not MemberAttendance.REMOTE_ONLY:
                    remote_count += 1
        if not fits:
            optional_missing.append(member.alias)
            continue
        available.append(member.alias)
        optional_available += 1
        if check.condition is not None:
            conditions.append(f"{member.alias}: {check.condition.value}")
        if check.stale:
            stale.append(member.alias)

    rooms = fitting_rooms(
        data.rooms, slot, defense.expected_audience, needs_hybrid, policy.buffer_minutes
    )
    if not rooms:
        blockers.append((ROOM_BLOCKER, BlockReason.NO_ROOM))

    return _SlotVerdict(
        blockers=blockers,
        available=available,
        optional_available=optional_available,
        optional_missing=optional_missing,
        conditions=conditions,
        stale=stale,
        hypothetical=hypothetical,
        rooms_free=len(rooms),
    )


# ---------------------------------------------------------------- the solver


def candidate_slots(defense: Defense, engine: PolicyEngine, config: SolverConfig) -> list[Slot]:
    """Every slot on the grid inside working hours, on working days of the window."""
    policy = engine.current()
    hours = policy.working_hours
    duration = timedelta(minutes=policy.duration_minutes[defense.degree_level])
    step = timedelta(minutes=config.grid_minutes)
    first = timedelta(hours=hours.start.hour, minutes=hours.start.minute)
    last = timedelta(hours=hours.end.hour, minutes=hours.end.minute) - duration

    slots: list[Slot] = []
    for day in dates_between(defense.window_start, defense.window_end):
        if weekday_of(day) not in hours.weekdays:
            continue
        offset = first
        while offset <= last:
            start = wall_to_utc(wall_time(day, offset), policy.timezone)
            # end = start + duration in real time, so the length is always exact.
            slots.append(Slot(start=start, end=start + duration))
            offset += step
    return slots


def slot_id(start: datetime, end: datetime) -> str:
    """A stable id for a slot: the same times always give the same id (interfaces.md T02)."""
    text = f"{start.isoformat()}/{end.isoformat()}"
    return "slot-" + hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def find_slots(data: SolverInput, engine: PolicyEngine, config: SolverConfig) -> SolverResult:
    """All feasible slots (best first) and all near-misses (earliest first)."""
    known_ids = {member.id for member in data.members}
    by_member: dict[str, list[AvailabilityStatement]] = {}
    for statement in data.statements:
        # A statement about someone who is not on this committee is ignored (scope).
        if statement.member_id in known_ids:
            by_member.setdefault(statement.member_id, []).append(statement)

    candidates = candidate_slots(data.defense, engine, config)
    summary: dict[str, int] = {}
    feasible: list[SlotOption] = []
    near_misses: list[NearMiss] = []

    for slot in candidates:
        violations = engine.check_slot(data.defense, slot, data.now)
        if violations:
            for code in sorted({v.code.value for v in violations}):
                summary[code] = summary.get(code, 0) + 1
            continue

        verdict = _evaluate_slot(slot, data, engine, config, by_member)
        for reason in sorted({reason.value for _, reason in verdict.blockers}):
            summary[reason] = summary.get(reason, 0) + 1

        if not verdict.blockers:
            feasible.append(_option(slot, verdict, engine, candidates))
        elif len(verdict.blockers) == 1:
            near_misses.append(
                NearMiss(
                    slot_id=slot_id(slot.start, slot.end),
                    start=slot.start,
                    end=slot.end,
                    blocked_by=verdict.blockers,
                )
            )

    feasible.sort(key=lambda option: (-option.score, option.start, option.slot_id))
    near_misses.sort(key=lambda miss: (miss.start, miss.slot_id))
    return SolverResult(
        feasible=feasible, near_misses=near_misses, infeasible_summary=dict(sorted(summary.items()))
    )


def _option(
    slot: Slot, verdict: _SlotVerdict, engine: PolicyEngine, candidates: list[Slot]
) -> SlotOption:
    return SlotOption(
        slot_id=slot_id(slot.start, slot.end),
        start=slot.start,
        end=slot.end,
        score=_score(slot, verdict.optional_available, len(verdict.stale), candidates),
        available=verdict.available,
        optional_missing=verdict.optional_missing,
        conditions=verdict.conditions,
        rooms_free=verdict.rooms_free,
        notice_deadline=engine.notice_deadline(slot),
        low_confidence_inputs=verdict.stale,
        hypothetical=verdict.hypothetical,
    )


def _score(slot: Slot, optional_available: int, stale_inputs: int, candidates: list[Slot]) -> float:
    """Deterministic score: more optional members, then fewer stale inputs, then earlier.

    earliness is 1.0 for the first candidate slot of the window and 0.0 for the last.
    """
    first, last = candidates[0].start, candidates[-1].start
    span = (last - first).total_seconds()
    earliness = 1.0 if span == 0 else 1.0 - (slot.start - first).total_seconds() / span
    score = (
        _OPTIONAL_MEMBER_POINTS * optional_available
        - _STALE_INPUT_PENALTY * stale_inputs
        + earliness
    )
    return round(score, 6)  # rounding keeps the number identical on every machine


def spread_out[T: (SlotOption, NearMiss)](options: list[T], limit: int) -> list[T]:
    """The first `limit` options that do not overlap each other, in the given order.

    Without this, the top 5 would often be 08:00, 08:15, 08:30, ... on the same
    morning, which gives the agent (and the student) no real choice.
    """
    picked: list[T] = []
    for option in options:
        if len(picked) == limit:
            break
        if not any(overlaps((option.start, option.end), (p.start, p.end)) for p in picked):
            picked.append(option)
    return picked
