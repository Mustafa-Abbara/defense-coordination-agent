"""The defense and member state machines follow docs/state_machine.md exactly (ST-02).

The strongest check here reads the transition tables from the design document
itself and compares them with the code, row by row. So the code cannot drift
away from the document without a test failing.
"""

import itertools
import logging
import re
from pathlib import Path

import pytest

from app.core.enums import DefenseEvent, DefenseStatus, MemberEvent, MemberStatus
from app.core.state_machine import (
    DEFENSE_TRANSITIONS,
    ESCALATABLE_STATES,
    MEMBER_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransitionError,
    member_transition,
    transition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_MACHINE_DOC = REPO_ROOT / "docs" / "state_machine.md"

# A table row in the doc looks like:  | `DRAFT` | `START_APPROVED` | `COLLECTING` |
# The RESUME row has *previous_status* as its target (no backticks).
ROW = re.compile(r"^\|\s*`(\w+)`\s*\|\s*`(\w+)`\s*\|\s*(`\w+`|\*previous_status\*)\s*\|\s*$")


def read_doc_table(heading: str) -> set[tuple[str, str, str]]:
    """Return the (from, event, to) rows of the table under `heading` in the doc."""
    lines = STATE_MACHINE_DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading)  # ValueError here means the heading was renamed
    rows = set()
    for line in lines[start + 1 :]:
        if line.startswith("#"):  # next heading: the table is over
            break
        match = ROW.match(line)
        if match:
            source, event, target = match.groups()
            rows.add((source, event, target.strip("`")))
    assert rows, f"no table rows found under {heading!r}"
    return rows


DOC_DEFENSE_ROWS = read_doc_table("### Defense transition table")
DOC_MEMBER_ROWS = read_doc_table("### Member transition table")


# ---------------------------------------------------------------- defense machine


def code_defense_rows() -> set[tuple[str, str, str]]:
    rows = {(s.value, e.value, t.value) for (s, e), t in DEFENSE_TRANSITIONS.items()}
    # RESUME is not a plain row in the code table: its target is previous_status.
    rows.add(("ESCALATED", "RESUME", "*previous_status*"))
    return rows


def test_defense_code_table_equals_doc_table() -> None:
    assert code_defense_rows() == DOC_DEFENSE_ROWS


@pytest.mark.parametrize(
    ("source", "event", "target"),
    sorted(row for row in DOC_DEFENSE_ROWS if "previous_status" not in row[2]),
)
def test_every_documented_defense_transition_succeeds(source: str, event: str, target: str) -> None:
    assert transition(DefenseStatus(source), DefenseEvent(event)) is DefenseStatus(target)


@pytest.mark.parametrize("previous", sorted(ESCALATABLE_STATES))
def test_resume_returns_to_previous_status(previous: DefenseStatus) -> None:
    result = transition(DefenseStatus.ESCALATED, DefenseEvent.RESUME, previous_status=previous)
    assert result is previous


def test_escalatable_states_match_the_doc() -> None:
    doc_sources = {s for s, e, _ in DOC_DEFENSE_ROWS if e == "ESCALATE"}
    assert {s.value for s in ESCALATABLE_STATES} == doc_sources


def test_resume_without_previous_status_raises() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(DefenseStatus.ESCALATED, DefenseEvent.RESUME)


@pytest.mark.parametrize(
    "previous",
    [
        DefenseStatus.DRAFT,  # cannot escalate from DRAFT, so cannot come back to it
        DefenseStatus.ESCALATED,  # would loop forever
        DefenseStatus.COMPLETED,  # terminal states are final
        DefenseStatus.CANCELLED,
        DefenseStatus.FAILED,
    ],
)
def test_resume_to_a_state_that_cannot_escalate_raises(previous: DefenseStatus) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(DefenseStatus.ESCALATED, DefenseEvent.RESUME, previous_status=previous)


def test_resume_is_only_legal_from_escalated() -> None:
    with pytest.raises(IllegalTransitionError):
        transition(
            DefenseStatus.COLLECTING,
            DefenseEvent.RESUME,
            previous_status=DefenseStatus.SCHEDULED,
        )


# Illegal moves a reviewer can read at a glance. Each one would skip a safety step.
NAMED_ILLEGAL_DEFENSE_MOVES = [
    (DefenseStatus.DRAFT, DefenseEvent.APPROVAL_GRANTED),  # book before any poll
    (DefenseStatus.DRAFT, DefenseEvent.SCHEDULE_PROPOSED),  # propose before collecting
    (DefenseStatus.DRAFT, DefenseEvent.ESCALATE),  # agent does not run in DRAFT
    (DefenseStatus.COLLECTING, DefenseEvent.APPROVAL_GRANTED),  # approve with no proposal
    (DefenseStatus.COLLECTING, DefenseEvent.ROOM_CONFIRMED_INVITES_SENT),  # book w/o approval
    (DefenseStatus.COLLECTING, DefenseEvent.DEFENSE_TIME_PASSED),
    (DefenseStatus.AWAITING_APPROVAL, DefenseEvent.ROOM_CONFIRMED_INVITES_SENT),
    (DefenseStatus.AWAITING_APPROVAL, DefenseEvent.SCHEDULE_PROPOSED),  # two pending SCHEDULEs
    (DefenseStatus.BOOKING, DefenseEvent.ALL_MANDATORY_CONFIRMED),  # confirm before invites
    (DefenseStatus.CONFIRMING, DefenseEvent.DEFENSE_TIME_PASSED),  # complete unconfirmed
    (DefenseStatus.CONFIRMING, DefenseEvent.SCHEDULE_PROPOSED),
    (DefenseStatus.SCHEDULED, DefenseEvent.APPROVAL_GRANTED),
    (DefenseStatus.RESCHEDULING, DefenseEvent.APPROVAL_GRANTED),  # skip the new approval
    (DefenseStatus.COLLECTING, DefenseEvent.WINDOW_PASSED),  # must escalate first
    (DefenseStatus.COMPLETED, DefenseEvent.CANCEL),
    (DefenseStatus.CANCELLED, DefenseEvent.START_APPROVED),
    (DefenseStatus.FAILED, DefenseEvent.RESUME),
    (DefenseStatus.ESCALATED, DefenseEvent.ESCALATE),
]


@pytest.mark.parametrize(("state", "event"), NAMED_ILLEGAL_DEFENSE_MOVES)
def test_named_illegal_defense_transitions_raise(state: DefenseStatus, event: DefenseEvent) -> None:
    with pytest.raises(IllegalTransitionError):
        transition(state, event, previous_status=DefenseStatus.COLLECTING)


def test_every_undocumented_defense_pair_raises() -> None:
    legal = {(s, e) for s, e, _ in DOC_DEFENSE_ROWS}
    checked = 0
    for state, event in itertools.product(DefenseStatus, DefenseEvent):
        if (state.value, event.value) in legal:
            continue
        with pytest.raises(IllegalTransitionError):
            transition(state, event, previous_status=DefenseStatus.COLLECTING)
        checked += 1
    assert checked >= 10  # the roadmap asks for at least 10 illegal transitions


def test_terminal_states_have_no_exits() -> None:
    assert TERMINAL_STATES == {
        DefenseStatus.COMPLETED,
        DefenseStatus.CANCELLED,
        DefenseStatus.FAILED,
    }
    for state, event in itertools.product(TERMINAL_STATES, DefenseEvent):
        with pytest.raises(IllegalTransitionError):
            transition(state, event, previous_status=DefenseStatus.COLLECTING)


def test_error_message_names_state_and_event() -> None:
    with pytest.raises(IllegalTransitionError) as caught:
        transition(DefenseStatus.DRAFT, DefenseEvent.APPROVAL_GRANTED)
    assert "DRAFT" in str(caught.value)
    assert "APPROVAL_GRANTED" in str(caught.value)
    assert caught.value.current is DefenseStatus.DRAFT
    assert caught.value.event is DefenseEvent.APPROVAL_GRANTED


def test_illegal_transition_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.state_machine"):
        with pytest.raises(IllegalTransitionError):
            transition(DefenseStatus.COMPLETED, DefenseEvent.CANCEL)
    assert "COMPLETED" in caplog.text
    assert "CANCEL" in caplog.text


# ---------------------------------------------------------------- untrusted input


@pytest.mark.parametrize("raw", ["APPROVAL_GRANTED", "approval_granted", "", "DROP TABLE"])
def test_raw_string_event_is_rejected(raw: str) -> None:
    # Rule 2: untrusted text never directly drives a state change. Only the enum
    # (created by deterministic code) is accepted, even if the string matches.
    with pytest.raises(TypeError):
        transition(DefenseStatus.AWAITING_APPROVAL, raw)  # type: ignore[arg-type]


def test_raw_string_state_is_rejected() -> None:
    with pytest.raises(TypeError):
        transition("AWAITING_APPROVAL", DefenseEvent.APPROVAL_GRANTED)  # type: ignore[arg-type]


def test_member_event_is_rejected_by_the_defense_machine() -> None:
    with pytest.raises(TypeError):
        transition(DefenseStatus.COLLECTING, MemberEvent.POLL_SENT)  # type: ignore[arg-type]


def test_defense_event_is_rejected_by_the_member_machine() -> None:
    with pytest.raises(TypeError):
        member_transition(MemberStatus.INVITED, DefenseEvent.CANCEL)  # type: ignore[arg-type]


# ---------------------------------------------------------------- member machine


def test_member_code_table_equals_doc_table() -> None:
    code_rows = {(s.value, e.value, t.value) for (s, e), t in MEMBER_TRANSITIONS.items()}
    assert code_rows == DOC_MEMBER_ROWS


@pytest.mark.parametrize(("source", "event", "target"), sorted(DOC_MEMBER_ROWS))
def test_every_documented_member_transition_succeeds(source: str, event: str, target: str) -> None:
    assert member_transition(MemberStatus(source), MemberEvent(event)) is MemberStatus(target)


NAMED_ILLEGAL_MEMBER_MOVES = [
    (MemberStatus.NOT_CONTACTED, MemberEvent.REPLY_RECEIVED),  # never asked
    (MemberStatus.NOT_CONTACTED, MemberEvent.INVITE_SENT),  # invite before poll
    (MemberStatus.AWAITING_REPLY, MemberEvent.CONFIRM_RECEIVED),  # confirm with no invite
    (MemberStatus.DEFERRED, MemberEvent.REMINDERS_EXHAUSTED),  # no reminders while deferred
    (MemberStatus.WITHDRAWN, MemberEvent.REPLY_RECEIVED),  # withdrawal is final here
    (MemberStatus.WITHDRAWN, MemberEvent.DEFERRAL_RECEIVED),
    (MemberStatus.DECLINED, MemberEvent.CONFIRM_RECEIVED),
    (MemberStatus.REPLIED, MemberEvent.CLARIFICATION_ASKED),  # not in the diagram (yet)
    (MemberStatus.INVITED, MemberEvent.POLL_SENT),
    (MemberStatus.NON_RESPONSIVE, MemberEvent.REMINDERS_EXHAUSTED),
]


@pytest.mark.parametrize(("state", "event"), NAMED_ILLEGAL_MEMBER_MOVES)
def test_named_illegal_member_transitions_raise(state: MemberStatus, event: MemberEvent) -> None:
    with pytest.raises(IllegalTransitionError):
        member_transition(state, event)


def test_every_undocumented_member_pair_raises() -> None:
    legal = {(s, e) for s, e, _ in DOC_MEMBER_ROWS}
    for state, event in itertools.product(MemberStatus, MemberEvent):
        if (state.value, event.value) in legal:
            continue
        with pytest.raises(IllegalTransitionError):
            member_transition(state, event)


def test_late_reply_from_non_responsive_member_is_processed() -> None:
    # Rule in state_machine.md: a late reply still counts.
    replied = member_transition(MemberStatus.NON_RESPONSIVE, MemberEvent.REPLY_RECEIVED)
    assert member_transition(replied, MemberEvent.ISSUES_FOUND) is MemberStatus.NEEDS_CLARIFICATION


def test_every_status_appears_in_the_doc_tables() -> None:
    # Guards against an enum value that the documents never mention.
    doc_defense_states = {s for s, _, _ in DOC_DEFENSE_ROWS} | {
        t for _, _, t in DOC_DEFENSE_ROWS if "previous_status" not in t
    }
    assert {s.value for s in DefenseStatus} == doc_defense_states
    doc_member_states = {s for s, _, _ in DOC_MEMBER_ROWS} | {t for _, _, t in DOC_MEMBER_ROWS}
    assert {s.value for s in MemberStatus} == doc_member_states
    assert {e.value for e in DefenseEvent} == {e for _, e, _ in DOC_DEFENSE_ROWS}
    assert {e.value for e in MemberEvent} == {e for _, e, _ in DOC_MEMBER_ROWS}
