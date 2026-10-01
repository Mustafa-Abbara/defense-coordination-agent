"""SlotSolver: feasible slots, near-misses, score (ST-03, FR-12).

Default world from builders.py: MSc, window Mon 16 - Fri 27 Nov 2026 (Beirut,
UTC+2), M1 advisor + M2 internal mandatory, M3 internal optional, everyone
available the whole window, one free hybrid room, now = 1 Nov.
Local 10:00 = 08:00 UTC.
"""

import random
from datetime import date, datetime, timedelta

import pytest
from builders import (
    NOW,
    committee,
    defense,
    engine,
    free_room,
    member,
    one_day,
    solver_config,
    solver_input,
    statement,
    utc,
    whole_window_available,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.enums import BlockReason, MemberStatus, Role, StatementStatus
from app.core.models import Slot
from app.services.intervals import contains, overlaps
from app.services.local_time import zone
from app.services.room_filter import RoomAvailability
from app.services.slot_solver import (
    SolverInput,
    SolverResult,
    candidate_slots,
    find_slots,
    slot_id,
    spread_out,
)

ENGINE = engine()
CONFIG = solver_config()
TUE_10_LOCAL = utc(2026, 11, 17, 8)  # Tue 17 Nov 10:00 Beirut


def solve(data: SolverInput) -> SolverResult:
    return find_slots(data, ENGINE, CONFIG)


def statements_with(*extra, members=None):
    members = members or committee()
    return [whole_window_available(m.id) for m in members] + list(extra)


def near_miss_at(result: SolverResult, start: datetime):
    return next(miss for miss in result.near_misses if miss.start == start)


# ---------------------------------------------------------------- the happy path


def test_everyone_free_gives_every_grid_slot() -> None:
    result = solve(solver_input())
    # 10 working days x 35 starts (08:00 ... 16:30 every 15 minutes).
    assert len(result.feasible) == 350
    assert result.near_misses == []
    best = result.feasible[0]
    assert best.start == utc(2026, 11, 16, 6)  # Mon 16 Nov 08:00 local: earliest
    assert best.available == ["M1", "M2", "M3"]
    assert best.rooms_free == 1
    assert best.notice_deadline == utc(2026, 11, 2, 6)
    assert best.hypothetical is False


def test_candidate_grid_is_15_minutes_and_ends_inside_working_hours() -> None:
    slots = candidate_slots(defense(), ENGINE, CONFIG)
    first_day = [s for s in slots if s.start.date() == date(2026, 11, 16)]
    assert first_day[0].start == utc(2026, 11, 16, 6)
    assert first_day[1].start - first_day[0].start == timedelta(minutes=15)
    assert first_day[-1].end == utc(2026, 11, 16, 16)  # 18:00 local


def test_slot_ids_are_stable_and_unique() -> None:
    first, second = solve(solver_input()), solve(solver_input())
    assert first == second  # same input -> identical output (reproducibility)
    ids = [option.slot_id for option in first.feasible]
    assert len(set(ids)) == len(ids)
    option = first.feasible[0]
    assert slot_id(option.start, option.end) == option.slot_id


def test_input_order_does_not_change_the_result() -> None:
    data = solver_input()
    shuffled = data.model_copy(
        update={"statements": random.Random(7).sample(data.statements, len(data.statements))}
    )
    assert solve(shuffled) == solve(data)


# ---------------------------------------------------------------- members


def test_unavailable_hour_makes_overlapping_slots_near_misses() -> None:
    busy = statement("m-2", "UNAVAILABLE", [(TUE_10_LOCAL, TUE_10_LOCAL + timedelta(hours=1))])
    result = solve(solver_input(statements=statements_with(busy)))
    assert near_miss_at(result, TUE_10_LOCAL).blocked_by == [("M2", BlockReason.UNAVAILABLE)]
    # A slot starting exactly when the busy hour ends is fine (half-open intervals).
    starts = {o.start for o in result.feasible}
    assert TUE_10_LOCAL + timedelta(hours=1) in starts
    assert TUE_10_LOCAL - timedelta(minutes=90) in starts  # ends exactly at 10:00


def test_unclear_available_statement_is_not_feasible() -> None:
    # FM-02: a vague "yes" is saved but not used as firm availability.
    unclear = [
        whole_window_available("m-1"),
        whole_window_available("m-2", confidence=0.5),
        whole_window_available("m-3"),
    ]
    result = solve(solver_input(statements=unclear))
    assert result.feasible == []
    assert {miss.blocked_by[0] for miss in result.near_misses} == {("M2", BlockReason.UNCLEAR)}


def test_open_issue_also_makes_a_statement_unclear() -> None:
    flagged = [
        whole_window_available("m-1"),
        whole_window_available("m-2", issues=["AMBIGUOUS_WEEK"]),
    ]
    result = solve(solver_input(statements=flagged))
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M2", BlockReason.UNCLEAR)]


def test_unclear_unavailable_statement_still_blocks() -> None:
    # Safe side: even a low-confidence "no" removes the slot.
    busy = statement("m-1", "UNAVAILABLE", [one_day(17)], confidence=0.2, issues=["AMBIGUOUS_DAY"])
    result = solve(solver_input(statements=statements_with(busy)))
    assert all(o.start.date() != date(2026, 11, 17) for o in result.feasible)


def test_exactly_at_the_threshold_counts() -> None:
    at_threshold = [whole_window_available("m-1"), whole_window_available("m-2", confidence=0.7)]
    assert len(solve(solver_input(statements=at_threshold)).feasible) == 350


def test_silent_member_is_no_reply_and_what_if_makes_it_hypothetical() -> None:
    members = [
        member("M1", Role.ADVISOR),
        member("M2", Role.INTERNAL, status=MemberStatus.AWAITING_REPLY),
    ]
    data = solver_input(members=members, statements=[whole_window_available("m-1")])
    result = solve(data)
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M2", BlockReason.NO_REPLY)]

    what_if = solve(data.model_copy(update={"what_if_pending_available": True}))
    assert len(what_if.feasible) == 350
    assert all(option.hypothetical for option in what_if.feasible)


def test_what_if_does_not_cover_members_who_never_got_the_poll() -> None:
    members = [member("M1", Role.ADVISOR), member("M2", status=MemberStatus.NOT_CONTACTED)]
    data = solver_input(
        members=members,
        statements=[whole_window_available("m-1")],
        what_if_pending_available=True,
    )
    assert solve(data).feasible == []


def test_member_who_named_other_days_is_not_stated() -> None:
    only_tuesday = statement("m-2", "AVAILABLE", [one_day(17)])
    data = solver_input(statements=[whole_window_available("m-1"), only_tuesday])
    result = solve(data)
    assert {o.start.date() for o in result.feasible} == {date(2026, 11, 17)}
    monday = near_miss_at(result, utc(2026, 11, 16, 6))
    assert monday.blocked_by == [("M2", BlockReason.NOT_STATED)]


def test_statement_must_contain_the_whole_slot() -> None:
    # "10:00-11:00 works" cannot hold a 90-minute defense.
    short = statement("m-2", "AVAILABLE", [(TUE_10_LOCAL, TUE_10_LOCAL + timedelta(hours=1))])
    data = solver_input(statements=[whole_window_available("m-1"), short])
    assert solve(data).feasible == []


def test_withdrawn_member_blocks_everything() -> None:
    members = [member("M1", Role.ADVISOR), member("M2", status=MemberStatus.WITHDRAWN)]
    result = solve(solver_input(members=members))
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M2", BlockReason.UNAVAILABLE)]
    withdrawal = statement("m-2", "WITHDRAWAL", [])
    result = solve(solver_input(statements=statements_with(withdrawal)))
    assert result.feasible == []


def test_inactive_statements_are_ignored() -> None:
    old_no = statement("m-1", "UNAVAILABLE", [one_day(17)], status=StatementStatus.SUPERSEDED)
    review = statement("m-2", "UNAVAILABLE", [one_day(18)], status=StatementStatus.NEEDS_REVIEW)
    result = solve(solver_input(statements=statements_with(old_no, review)))
    assert len(result.feasible) == 350


def test_statement_about_someone_outside_the_committee_is_ignored() -> None:
    stranger = statement("m-99", "UNAVAILABLE", [one_day(17)])
    assert len(solve(solver_input(statements=statements_with(stranger))).feasible) == 350


def test_declined_slot_blocks_like_unavailable() -> None:
    decline = statement("m-1", "DECLINE", [(TUE_10_LOCAL, TUE_10_LOCAL + timedelta(minutes=90))])
    result = solve(solver_input(statements=statements_with(decline)))
    assert near_miss_at(result, TUE_10_LOCAL).blocked_by == [("M1", BlockReason.UNAVAILABLE)]


# ---------------------------------------------------------------- stale inputs and score


def test_stale_statement_is_usable_but_flagged_and_ranked_lower() -> None:
    old = NOW - timedelta(days=11)  # staleness_days = 10
    stale_on_monday = [
        whole_window_available("m-1"),
        statement("m-2", "AVAILABLE", [one_day(16)], observed_at=old),
        statement("m-2", "AVAILABLE", [one_day(17)]),
        whole_window_available("m-3"),
    ]
    result = solve(solver_input(statements=stale_on_monday))
    monday = [o for o in result.feasible if o.start.date() == date(2026, 11, 16)]
    tuesday = [o for o in result.feasible if o.start.date() == date(2026, 11, 17)]
    assert monday and all(o.low_confidence_inputs == ["M2"] for o in monday)
    assert all(o.low_confidence_inputs == [] for o in tuesday)
    # Fresh Tuesday ranks above stale (earlier) Monday.
    assert result.feasible[0].start.date() == date(2026, 11, 17)


def test_optional_member_raises_the_score_but_never_blocks() -> None:
    optional_tuesday_only = [
        whole_window_available("m-1"),
        whole_window_available("m-2"),
        statement("m-3", "AVAILABLE", [one_day(24)]),
    ]
    result = solve(solver_input(statements=optional_tuesday_only))
    assert len(result.feasible) == 350
    assert result.feasible[0].start.date() == date(2026, 11, 24)  # M3 is there
    monday = next(o for o in result.feasible if o.start == utc(2026, 11, 16, 6))
    assert monday.optional_missing == ["M3"]
    assert result.feasible[0].score > monday.score


# ---------------------------------------------------------------- conditions and rooms


def test_hybrid_condition_needs_a_hybrid_room() -> None:
    hybrid = whole_window_available("m-2", kind="CONDITIONAL", condition="HYBRID_REQUIRED")
    statements = [whole_window_available("m-1"), hybrid]
    no_hybrid_room = [
        RoomAvailability(room=free_room().room.model_copy(update={"hybrid_capable": False}))
    ]
    result = solve(solver_input(statements=statements, rooms=no_hybrid_room))
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("ROOM", BlockReason.NO_ROOM)]

    result = solve(solver_input(statements=statements))  # default room is hybrid
    assert result.feasible[0].conditions == ["M2: HYBRID_REQUIRED"]


def test_unconditional_statement_is_preferred_over_a_conditional_one() -> None:
    both = [
        whole_window_available("m-1"),
        whole_window_available("m-2", kind="CONDITIONAL", condition="HYBRID_REQUIRED"),
        whole_window_available("m-2"),
    ]
    assert solve(solver_input(statements=both)).feasible[0].conditions == []


def test_condition_impossible_in_an_in_person_defense() -> None:
    hybrid = whole_window_available("m-2", kind="CONDITIONAL", condition="HYBRID_REQUIRED")
    data = solver_input(
        defense=defense(attendance_mode="IN_PERSON"),
        statements=[whole_window_available("m-1"), hybrid],
    )
    result = solve(data)
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M2", BlockReason.CONDITION)]


@pytest.mark.parametrize("condition", ["IF_MEMBER_PRESENT", "OTHER", None])
def test_conditions_code_cannot_check_block(condition: str | None) -> None:
    unclear_condition = whole_window_available("m-2", kind="CONDITIONAL", condition=condition)
    result = solve(solver_input(statements=[whole_window_available("m-1"), unclear_condition]))
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M2", BlockReason.CONDITION)]


def test_remote_only_condition_follows_the_policy() -> None:
    # remote_allowed_roles = [EXTERNAL], max_remote_members = 1.
    members = [
        member("M1", Role.ADVISOR),
        member("M2", Role.EXTERNAL),
        member("M3", Role.EXTERNAL),
        member("M4", Role.INTERNAL),
    ]
    remote = {"kind": "CONDITIONAL", "condition": "REMOTE_ONLY"}
    statements = [
        whole_window_available("m-1"),
        whole_window_available("m-2", **remote),
        whole_window_available("m-3"),
        whole_window_available("m-4"),
    ]
    result = solve(solver_input(members=members, statements=statements))
    assert result.feasible[0].conditions == ["M2: REMOTE_ONLY"]

    # A second remote member: no remote place left.
    statements[2] = whole_window_available("m-3", **remote)
    result = solve(solver_input(members=members, statements=statements))
    assert result.feasible == []
    assert result.near_misses[0].blocked_by == [("M3", BlockReason.CONDITION)]

    # An INTERNAL member may not attend remotely at all.
    statements[2] = whole_window_available("m-3")
    statements[3] = whole_window_available("m-4", **remote)
    statements[1] = whole_window_available("m-2")
    result = solve(solver_input(members=members, statements=statements))
    assert result.near_misses[0].blocked_by == [("M4", BlockReason.CONDITION)]


def test_optional_member_with_a_condition_never_changes_the_room() -> None:
    optional_hybrid = whole_window_available("m-3", kind="CONDITIONAL", condition="HYBRID_REQUIRED")
    non_hybrid = [
        RoomAvailability(room=free_room().room.model_copy(update={"hybrid_capable": False}))
    ]
    data = solver_input(
        statements=[whole_window_available("m-1"), whole_window_available("m-2"), optional_hybrid],
        rooms=non_hybrid,
    )
    result = solve(data)
    assert len(result.feasible) == 350
    assert result.feasible[0].optional_missing == ["M3"]


def test_optional_remote_member_needs_a_remote_place_and_an_allowed_role() -> None:
    # The slot is hybrid anyway (HYBRID_REQUIRED). One remote place (max_remote_members = 1).
    members = [
        member("M1", Role.ADVISOR),
        member("M2", Role.INTERNAL),
        member("M3", Role.EXTERNAL, is_mandatory=False),
        member("M4", Role.EXTERNAL, is_mandatory=False),
        member("M5", Role.INTERNAL, is_mandatory=False),
    ]
    remote = {"kind": "CONDITIONAL", "condition": "REMOTE_ONLY"}
    stale = NOW - timedelta(days=30)
    statements = [
        whole_window_available("m-1"),
        whole_window_available("m-2"),
        whole_window_available("m-3", observed_at=stale, **remote),  # takes the place
        whole_window_available("m-4", **remote),  # no place left
        whole_window_available("m-5", **remote),  # INTERNAL may not be remote
    ]
    data = solver_input(
        defense=defense(attendance_mode="HYBRID_REQUIRED"), members=members, statements=statements
    )
    best = solve(data).feasible[0]
    assert best.available == ["M1", "M2", "M3"]
    assert best.optional_missing == ["M4", "M5"]
    assert best.conditions == ["M3: REMOTE_ONLY"]
    assert best.low_confidence_inputs == ["M3"]


def test_busy_room_and_no_room_at_all() -> None:
    busy_tuesday = RoomAvailability(room=free_room().room, busy=[one_day(17)])
    result = solve(solver_input(rooms=[busy_tuesday]))
    assert all(o.start.date() != date(2026, 11, 17) for o in result.feasible)
    assert near_miss_at(result, TUE_10_LOCAL).blocked_by == [("ROOM", BlockReason.NO_ROOM)]

    result = solve(solver_input(rooms=[]))
    assert result.feasible == []
    assert result.infeasible_summary == {"NO_ROOM": 350}


def test_audience_bigger_than_every_room() -> None:
    result = solve(solver_input(defense=defense(expected_audience=500)))
    assert result.feasible == []


# ---------------------------------------------------------------- near-misses and summary


def test_two_blockers_is_not_a_near_miss_but_is_counted() -> None:
    busy = [
        statement("m-1", "UNAVAILABLE", [one_day(17)]),
        statement("m-2", "UNAVAILABLE", [one_day(17)]),
    ]
    result = solve(solver_input(statements=statements_with(*busy)))
    assert all(miss.start.date() != date(2026, 11, 17) for miss in result.near_misses)
    assert result.infeasible_summary == {"UNAVAILABLE": 35}


def test_notice_deadline_removes_early_slots() -> None:
    # now = Thu 5 Nov 12:00 UTC: slots on Thu 19 Nov before 14:00 local are too late
    # to announce with 14 days' notice; Mon 16 - Wed 18 Nov are all too late.
    result = solve(solver_input(now=utc(2026, 11, 5, 12)))
    assert result.infeasible_summary["NOTICE_DEADLINE_PASSED"] == 3 * 35 + 24
    assert result.feasible[0].start == utc(2026, 11, 19, 12)


def test_near_misses_are_sorted_by_time() -> None:
    busy = statement("m-2", "UNAVAILABLE", [one_day(18), one_day(17)])
    result = solve(solver_input(statements=statements_with(busy)))
    starts = [miss.start for miss in result.near_misses]
    assert starts == sorted(starts)


def test_spread_out_picks_non_overlapping_options() -> None:
    result = solve(solver_input())
    top = spread_out(result.feasible, 5)
    assert len(top) == 5
    for i, first in enumerate(top):
        for second in top[i + 1 :]:
            assert not overlaps((first.start, first.end), (second.start, second.end))
    assert spread_out(result.feasible, 0) == []
    assert spread_out([], 5) == []


def test_solver_input_rejects_naive_time_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        solver_input(now=datetime(2026, 11, 1, 8))  # noqa: DTZ001
    with pytest.raises(ValidationError):
        SolverInput.model_validate({**solver_input().model_dump(), "approve": True})


# ---------------------------------------------------------------- properties (acceptance #2)

SMALL_WINDOW = {"window_start": date(2026, 11, 16), "window_end": date(2026, 11, 18)}
base = utc(2026, 11, 15, 20)  # a little before the window, in UTC
block = st.tuples(st.integers(0, 4 * 24 * 4), st.integers(1, 32)).map(
    lambda pair: (
        base + timedelta(minutes=15 * pair[0]),
        base + timedelta(minutes=15 * (pair[0] + pair[1])),
    )
)
kind = st.sampled_from(["UNAVAILABLE", "UNAVAILABLE", "AVAILABLE", "CONDITIONAL", "DECLINE"])
condition = st.sampled_from([None, "HYBRID_REQUIRED", "REMOTE_ONLY", "IF_MEMBER_PRESENT"])
member_statement = st.tuples(
    st.sampled_from(["m-1", "m-2", "m-3"]),
    kind,
    st.lists(block, min_size=1, max_size=3),
    st.sampled_from([0.4, 0.7, 0.95]),
    condition,
)


def build_statements(raw: list) -> list:
    return [
        statement(m_id, k, intervals, confidence=c, condition=cond)
        for m_id, k, intervals, c, cond in raw
    ]


@given(
    raw=st.lists(member_statement, max_size=10),
    broadly_free=st.lists(st.sampled_from([True, True, True, False]), min_size=3, max_size=3),
    now_offset_hours=st.integers(-24 * 30, 24 * 6),
    hybrid_room=st.booleans(),
    mode=st.sampled_from(["IN_PERSON", "HYBRID_ALLOWED", "HYBRID_REQUIRED"]),
)
def test_feasible_slots_respect_every_hard_constraint(
    raw: list, broadly_free: list[bool], now_offset_hours: int, hybrid_room: bool, mode: str
) -> None:
    # Most members say "any time works" and then add random busy times, random
    # conditions, and vague answers on top, so many runs have feasible slots to check.
    statements = [
        whole_window_available(m_id)
        for m_id, free in zip(["m-1", "m-2", "m-3"], broadly_free, strict=True)
        if free
    ] + build_statements(raw)
    now = NOW + timedelta(hours=now_offset_hours)
    rooms = [
        RoomAvailability(room=free_room().room.model_copy(update={"hybrid_capable": hybrid_room}))
    ]
    the_defense = defense(attendance_mode=mode, **SMALL_WINDOW)
    data = solver_input(defense=the_defense, statements=statements, rooms=rooms, now=now)
    result = solve(data)

    mandatory_ids = {m.id for m in data.members if m.is_mandatory}
    alias_of = {m.id: m.alias for m in data.members}
    for option in result.feasible:
        slot = Slot(start=option.start, end=option.end)
        # Policy: duration, working hours, window, term, notice (check_slot is independent).
        assert ENGINE.check_slot(the_defense, slot, now) == []
        # On the 15-minute grid, in local time.
        assert option.start.astimezone(zone(ENGINE.current().timezone)).minute % 15 == 0
        # No mandatory member is busy at that time.
        for s in statements:
            if s.member_id in mandatory_ids and s.kind in ("UNAVAILABLE", "DECLINE"):
                assert not any(overlaps(i, (slot.start, slot.end)) for i in s.intervals_utc)
        # Every mandatory member has a confident statement that holds the whole slot.
        for m_id in mandatory_ids:
            assert alias_of[m_id] in option.available
            assert any(
                s.member_id == m_id
                and s.kind in ("AVAILABLE", "CONDITIONAL")
                and s.confidence >= CONFIG.confidence_threshold
                and any(contains(i, (slot.start, slot.end)) for i in s.intervals_utc)
                for s in statements
            )
        # A slot that needs hybrid only uses hybrid rooms; an in-person defense has no conditions.
        if option.conditions:
            assert hybrid_room and mode != "IN_PERSON"
    for miss in result.near_misses:
        assert len(miss.blocked_by) == 1
    feasible_ids = {o.slot_id for o in result.feasible}
    assert not feasible_ids & {m.slot_id for m in result.near_misses}
