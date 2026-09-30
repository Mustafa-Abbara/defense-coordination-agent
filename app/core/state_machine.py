"""The two state machines as lookup tables (ST-02).

Source of truth: docs/state_machine.md -> "Transition tables". A test reads the
tables from that document and checks that the dictionaries below are equal.

How it works: each table maps (current status, event) -> next status.
A pair that is not in the table is illegal: we log it and raise
IllegalTransitionError. Nothing else in the code may set a status, so an
illegal move (for example "book the room" while nothing was approved) cannot
happen by accident, whatever a handler, a tool, or the LLM asks for.

These functions do not save anything. The orchestrator (ST-04) calls them,
saves the new status, and writes the event to the event log.
"""

import logging
from typing import NoReturn

from app.core.enums import DefenseEvent, DefenseStatus, MemberEvent, MemberStatus

logger = logging.getLogger(__name__)

D = DefenseStatus  # short names keep the tables readable
DE = DefenseEvent
M = MemberStatus
ME = MemberEvent


class IllegalTransitionError(ValueError):
    """Raised when (state, event) is not an allowed move."""

    def __init__(
        self,
        current: DefenseStatus | MemberStatus,
        event: DefenseEvent | MemberEvent,
        reason: str = "not in the transition table",
    ) -> None:
        self.current = current
        self.event = event
        super().__init__(f"Illegal transition: {current.value} --{event.value}--> ({reason})")


# ---------------------------------------------------------------- defense machine

# States from which the agent or a deterministic trigger may escalate.
# RESUME may only return to one of these.
ESCALATABLE_STATES: frozenset[DefenseStatus] = frozenset(
    {D.COLLECTING, D.AWAITING_APPROVAL, D.BOOKING, D.CONFIRMING, D.SCHEDULED, D.RESCHEDULING}
)

# No move leaves these.
TERMINAL_STATES: frozenset[DefenseStatus] = frozenset({D.COMPLETED, D.CANCELLED, D.FAILED})

# Every row is written out, in the same order as the table in the document,
# so a reader can compare them line by line.
# ESCALATED + RESUME is not here: its target depends on previous_status
# (see transition() below).
DEFENSE_TRANSITIONS: dict[tuple[DefenseStatus, DefenseEvent], DefenseStatus] = {
    # Main path
    (D.DRAFT, DE.START_APPROVED): D.COLLECTING,
    (D.COLLECTING, DE.SCHEDULE_PROPOSED): D.AWAITING_APPROVAL,
    (D.AWAITING_APPROVAL, DE.APPROVAL_GRANTED): D.BOOKING,
    (D.AWAITING_APPROVAL, DE.APPROVAL_REJECTED): D.COLLECTING,
    (D.AWAITING_APPROVAL, DE.APPROVAL_EXPIRED): D.COLLECTING,
    (D.AWAITING_APPROVAL, DE.APPROVAL_STALE): D.COLLECTING,
    (D.BOOKING, DE.ROOM_CONFIRMED_INVITES_SENT): D.CONFIRMING,
    (D.BOOKING, DE.ROOM_REJECTED): D.COLLECTING,
    (D.CONFIRMING, DE.ALL_MANDATORY_CONFIRMED): D.SCHEDULED,
    (D.CONFIRMING, DE.DISRUPTED): D.RESCHEDULING,
    (D.SCHEDULED, DE.DEFENSE_TIME_PASSED): D.COMPLETED,
    (D.SCHEDULED, DE.DISRUPTED): D.RESCHEDULING,
    (D.RESCHEDULING, DE.SCHEDULE_PROPOSED): D.AWAITING_APPROVAL,
    (D.RESCHEDULING, DE.MORE_REPLIES_NEEDED): D.COLLECTING,
    # Escalation (agent T10 or a deterministic trigger)
    (D.COLLECTING, DE.ESCALATE): D.ESCALATED,
    (D.AWAITING_APPROVAL, DE.ESCALATE): D.ESCALATED,
    (D.BOOKING, DE.ESCALATE): D.ESCALATED,
    (D.CONFIRMING, DE.ESCALATE): D.ESCALATED,
    (D.SCHEDULED, DE.ESCALATE): D.ESCALATED,
    (D.RESCHEDULING, DE.ESCALATE): D.ESCALATED,
    (D.ESCALATED, DE.WINDOW_PASSED): D.FAILED,
    # Student cancels (any non-terminal state)
    (D.DRAFT, DE.CANCEL): D.CANCELLED,
    (D.COLLECTING, DE.CANCEL): D.CANCELLED,
    (D.AWAITING_APPROVAL, DE.CANCEL): D.CANCELLED,
    (D.BOOKING, DE.CANCEL): D.CANCELLED,
    (D.CONFIRMING, DE.CANCEL): D.CANCELLED,
    (D.SCHEDULED, DE.CANCEL): D.CANCELLED,
    (D.RESCHEDULING, DE.CANCEL): D.CANCELLED,
    (D.ESCALATED, DE.CANCEL): D.CANCELLED,
    # Broken event-log hash chain (TH-06, SEC-08): stop safely from anywhere
    (D.DRAFT, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.COLLECTING, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.AWAITING_APPROVAL, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.BOOKING, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.CONFIRMING, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.SCHEDULED, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.RESCHEDULING, DE.INTEGRITY_FAILURE): D.FAILED,
    (D.ESCALATED, DE.INTEGRITY_FAILURE): D.FAILED,
}


def transition(
    current: DefenseStatus,
    event: DefenseEvent,
    previous_status: DefenseStatus | None = None,
) -> DefenseStatus:
    """Return the defense status after `event`, or raise IllegalTransitionError.

    `previous_status` is only used for RESUME: it is Defense.previous_status,
    the status saved when the defense entered ESCALATED.
    """
    # Only enums made by our own code are accepted. A StrEnum is equal to its
    # string, so without this check the raw text "APPROVAL_GRANTED" (for
    # example copied from an email) would find a row in the table (rule 2).
    if not isinstance(current, DefenseStatus) or not isinstance(event, DefenseEvent):
        raise TypeError("transition() needs a DefenseStatus and a DefenseEvent")

    if current is D.ESCALATED and event is DE.RESUME:
        if previous_status not in ESCALATABLE_STATES:
            _reject(current, event, "previous_status is missing or cannot be resumed")
        return previous_status

    next_status = DEFENSE_TRANSITIONS.get((current, event))
    if next_status is None:
        _reject(current, event)
    return next_status


# ---------------------------------------------------------------- member machine

# "any -> DEFERRED" and "any -> WITHDRAWN" in the diagram: every state except
# NOT_CONTACTED (no thread token yet) and WITHDRAWN (final for the member).
_CONTACTED_STATES = (
    M.AWAITING_REPLY,
    M.REPLIED,
    M.NON_RESPONSIVE,
    M.NEEDS_CLARIFICATION,
    M.CLARIFICATION_SENT,
    M.DEFERRED,
    M.INVITED,
    M.CONFIRMED,
    M.DECLINED,
)

MEMBER_TRANSITIONS: dict[tuple[MemberStatus, MemberEvent], MemberStatus] = {
    (M.NOT_CONTACTED, ME.POLL_SENT): M.AWAITING_REPLY,
    (M.AWAITING_REPLY, ME.REPLY_RECEIVED): M.REPLIED,
    (M.AWAITING_REPLY, ME.REMINDERS_EXHAUSTED): M.NON_RESPONSIVE,
    (M.NON_RESPONSIVE, ME.REPLY_RECEIVED): M.REPLIED,  # a late reply still counts
    (M.REPLIED, ME.ISSUES_FOUND): M.NEEDS_CLARIFICATION,
    (M.NEEDS_CLARIFICATION, ME.CLARIFICATION_ASKED): M.CLARIFICATION_SENT,
    (M.CLARIFICATION_SENT, ME.REPLY_RECEIVED): M.REPLIED,
    (M.REPLIED, ME.INVITE_SENT): M.INVITED,
    (M.INVITED, ME.CONFIRM_RECEIVED): M.CONFIRMED,
    (M.INVITED, ME.DECLINE_RECEIVED): M.DECLINED,
    (M.CONFIRMED, ME.DECLINE_RECEIVED): M.DECLINED,  # "conflict after all"
    (M.DEFERRED, ME.RECHECK_DUE): M.AWAITING_REPLY,
}
# The two "any" rules, written as one row per state (9 + 9 rows).
for _state in _CONTACTED_STATES:
    MEMBER_TRANSITIONS[(_state, ME.DEFERRAL_RECEIVED)] = M.DEFERRED
    MEMBER_TRANSITIONS[(_state, ME.WITHDRAWAL_RECEIVED)] = M.WITHDRAWN


def member_transition(current: MemberStatus, event: MemberEvent) -> MemberStatus:
    """Return the member status after `event`, or raise IllegalTransitionError."""
    if not isinstance(current, MemberStatus) or not isinstance(event, MemberEvent):
        raise TypeError("member_transition() needs a MemberStatus and a MemberEvent")

    next_status = MEMBER_TRANSITIONS.get((current, event))
    if next_status is None:
        _reject(current, event)
    return next_status


# ---------------------------------------------------------------- shared


def _reject(
    current: DefenseStatus | MemberStatus,
    event: DefenseEvent | MemberEvent,
    reason: str = "not in the transition table",
) -> NoReturn:
    # Only enum names are logged: no member data, nothing from an email.
    error = IllegalTransitionError(current, event, reason)
    logger.warning("%s", error)
    raise error
