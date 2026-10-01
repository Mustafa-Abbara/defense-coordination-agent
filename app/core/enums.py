"""Every fixed list of values in the system (ST-02).

Source: docs/data_model.md (fields) and docs/state_machine.md (statuses and events).
StrEnum values are plain strings, so they are easy to store in SQLite, to show
in the UI, and to read in logs. A value that is not in the list is rejected by
the Pydantic models.
"""

from enum import StrEnum

# ---------------------------------------------------------------- state machines


class DefenseStatus(StrEnum):
    """Where the whole workflow stands (state_machine.md -> Defense states)."""

    DRAFT = "DRAFT"
    COLLECTING = "COLLECTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BOOKING = "BOOKING"
    CONFIRMING = "CONFIRMING"
    SCHEDULED = "SCHEDULED"
    RESCHEDULING = "RESCHEDULING"
    ESCALATED = "ESCALATED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class DefenseEvent(StrEnum):
    """Something that happened and may move the defense to another status.

    The exact moves are in state_machine.md -> "Defense transition table".
    """

    START_APPROVED = "START_APPROVED"  # student approved the first poll (AP-01)
    SCHEDULE_PROPOSED = "SCHEDULE_PROPOSED"  # T07 / T09 created a SCHEDULE approval
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_STALE = "APPROVAL_STALE"
    ROOM_CONFIRMED_INVITES_SENT = "ROOM_CONFIRMED_INVITES_SENT"
    ROOM_REJECTED = "ROOM_REJECTED"
    ALL_MANDATORY_CONFIRMED = "ALL_MANDATORY_CONFIRMED"
    DISRUPTED = "DISRUPTED"  # decline, room lost, requirement changed, notice missed
    DEFENSE_TIME_PASSED = "DEFENSE_TIME_PASSED"
    MORE_REPLIES_NEEDED = "MORE_REPLIES_NEEDED"
    ESCALATE = "ESCALATE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    WINDOW_PASSED = "WINDOW_PASSED"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


class MemberStatus(StrEnum):
    """Where one member's conversation stands (state_machine.md -> Member states)."""

    NOT_CONTACTED = "NOT_CONTACTED"
    AWAITING_REPLY = "AWAITING_REPLY"
    REPLIED = "REPLIED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    CLARIFICATION_SENT = "CLARIFICATION_SENT"
    NON_RESPONSIVE = "NON_RESPONSIVE"
    INVITED = "INVITED"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    DEFERRED = "DEFERRED"
    WITHDRAWN = "WITHDRAWN"


class MemberEvent(StrEnum):
    """Something that happened to one member (state_machine.md -> Member transition table)."""

    POLL_SENT = "POLL_SENT"
    REPLY_RECEIVED = "REPLY_RECEIVED"
    ISSUES_FOUND = "ISSUES_FOUND"
    CLARIFICATION_ASKED = "CLARIFICATION_ASKED"
    REMINDERS_EXHAUSTED = "REMINDERS_EXHAUSTED"
    INVITE_SENT = "INVITE_SENT"
    CONFIRM_RECEIVED = "CONFIRM_RECEIVED"
    DECLINE_RECEIVED = "DECLINE_RECEIVED"
    DEFERRAL_RECEIVED = "DEFERRAL_RECEIVED"
    RECHECK_DUE = "RECHECK_DUE"
    WITHDRAWAL_RECEIVED = "WITHDRAWAL_RECEIVED"


# ---------------------------------------------------------------- defense and committee


class DegreeLevel(StrEnum):
    MSC = "MSC"
    PHD = "PHD"


class AttendanceMode(StrEnum):
    """How the defense itself is held."""

    IN_PERSON = "IN_PERSON"
    HYBRID_ALLOWED = "HYBRID_ALLOWED"
    HYBRID_REQUIRED = "HYBRID_REQUIRED"


class Role(StrEnum):
    """Committee roles. The values are ASSUMPTION A-04 (no source yet)."""

    ADVISOR = "ADVISOR"
    CO_ADVISOR = "CO_ADVISOR"
    CHAIR = "CHAIR"
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class MemberAttendance(StrEnum):
    """How one member will attend."""

    IN_PERSON = "IN_PERSON"
    REMOTE_OK = "REMOTE_OK"
    REMOTE_ONLY = "REMOTE_ONLY"


class SubstituteApprover(StrEnum):
    """Who must approve a substitute member (policy.yaml, A-11). Outside the system."""

    ADVISOR = "ADVISOR"
    COORDINATOR = "COORDINATOR"


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


class PartOfDay(StrEnum):
    """Named parts of the day that the resolver maps to clock times (A-20)."""

    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"


# ---------------------------------------------------------------- availability statements


class StatementSource(StrEnum):
    EMAIL = "EMAIL"
    MANUAL = "MANUAL"
    CALENDAR = "CALENDAR"


class StatementKind(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    CONDITIONAL = "CONDITIONAL"
    DEFERRAL = "DEFERRAL"
    WITHDRAWAL = "WITHDRAWAL"
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"


class StatementCondition(StrEnum):
    HYBRID_REQUIRED = "HYBRID_REQUIRED"
    REMOTE_ONLY = "REMOTE_ONLY"
    IF_MEMBER_PRESENT = "IF_MEMBER_PRESENT"
    OTHER = "OTHER"


class StatementStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class IssueCode(StrEnum):
    """Problems found in a statement. Only these codes ever reach the planner."""

    AMBIGUOUS_DAY = "AMBIGUOUS_DAY"
    AMBIGUOUS_WEEK = "AMBIGUOUS_WEEK"
    WEEKDAY_DATE_MISMATCH = "WEEKDAY_DATE_MISMATCH"
    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    CONTRADICTS_PREVIOUS = "CONTRADICTS_PREVIOUS"
    CONDITION_UNCLEAR = "CONDITION_UNCLEAR"
    TZ_UNCLEAR = "TZ_UNCLEAR"
    UNPARSEABLE = "UNPARSEABLE"
    SUSPICIOUS_INSTRUCTION = "SUSPICIOUS_INSTRUCTION"
    TRUNCATED = "TRUNCATED"  # body cut at the size cap (interfaces.md, pipeline stage 1)


# ---------------------------------------------------------------- rooms, messages, approvals


class BookingStatus(StrEnum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"


class MessageDirection(StrEnum):
    IN = "IN"
    OUT = "OUT"


class ProcessingStatus(StrEnum):
    NEW = "NEW"
    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUARANTINED = "QUARANTINED"
    DUPLICATE = "DUPLICATE"
    IGNORED = "IGNORED"


class MessagePurpose(StrEnum):
    """Why an outbound message was sent (OUT messages only)."""

    POLL = "POLL"
    REMINDER = "REMINDER"
    CLARIFICATION = "CLARIFICATION"
    INVITE = "INVITE"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    SUBSTITUTE_REQUEST = "SUBSTITUTE_REQUEST"
    CANCEL = "CANCEL"


class ApprovalActionType(StrEnum):
    START_POLL = "START_POLL"
    SCHEDULE = "SCHEDULE"  # book + invite, one bundle (AP-07)
    ANNOUNCE = "ANNOUNCE"
    REPOLL = "REPOLL"
    SUBSTITUTE_REQUEST = "SUBSTITUTE_REQUEST"
    RESCHEDULE = "RESCHEDULE"
    CANCEL = "CANCEL"


class RiskTier(StrEnum):
    """Approval tiers from approval_policy.md."""

    R0 = "R0"  # automatic, internal
    R1 = "R1"  # automatic with guardrails
    R2 = "R2"  # needs student approval
    R3 = "R3"  # never allowed


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    STALE = "STALE"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


# ---------------------------------------------------------------- timers, traces, users


class TimerKind(StrEnum):
    REMINDER = "REMINDER"
    RECHECK = "RECHECK"
    RESPONSE_DEADLINE = "RESPONSE_DEADLINE"
    APPROVAL_EXPIRY = "APPROVAL_EXPIRY"
    NOTICE_DEADLINE = "NOTICE_DEADLINE"
    WINDOW_END = "WINDOW_END"
    AGENT_WAKEUP = "AGENT_WAKEUP"


class TimerStatus(StrEnum):
    PENDING = "PENDING"
    FIRED = "FIRED"
    CANCELLED = "CANCELLED"


class SpanKind(StrEnum):
    LLM = "LLM"
    TOOL = "TOOL"
    HANDLER = "HANDLER"
    VALIDATION = "VALIDATION"


class SpanOutcome(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"


class UserRole(StrEnum):
    STUDENT = "STUDENT"
    OBSERVER = "OBSERVER"
    ADMIN = "ADMIN"


# ---------------------------------------------------------------- deterministic services (ST-03)


class ViolationCode(StrEnum):
    """A broken policy rule, found by the policy engine (services/policy_engine.py)."""

    # Setup checks (FR-02), run before coordination starts.
    REQUIRED_ROLE_MISSING = "REQUIRED_ROLE_MISSING"  # no mandatory member has this role
    COMMITTEE_TOO_SMALL = "COMMITTEE_TOO_SMALL"
    COMMITTEE_TOO_LARGE = "COMMITTEE_TOO_LARGE"  # more than 7 (aliases M1-M7)
    DUPLICATE_EMAIL = "DUPLICATE_EMAIL"
    DUPLICATE_ALIAS = "DUPLICATE_ALIAS"
    MEMBER_OF_OTHER_DEFENSE = "MEMBER_OF_OTHER_DEFENSE"
    WINDOW_OUTSIDE_TERM = "WINDOW_OUTSIDE_TERM"
    WINDOW_TOO_SHORT_FOR_NOTICE = "WINDOW_TOO_SHORT_FOR_NOTICE"
    NO_WORKING_DAY_IN_WINDOW = "NO_WORKING_DAY_IN_WINDOW"
    REMOTE_ROLE_NOT_ALLOWED = "REMOTE_ROLE_NOT_ALLOWED"
    TOO_MANY_REMOTE_MEMBERS = "TOO_MANY_REMOTE_MEMBERS"
    REMOTE_MEMBER_IN_PERSON_DEFENSE = "REMOTE_MEMBER_IN_PERSON_DEFENSE"
    # Slot checks (check_slot), run by the solver, T07, and the executor.
    WRONG_DURATION = "WRONG_DURATION"
    NOT_A_WORKING_DAY = "NOT_A_WORKING_DAY"
    OUTSIDE_WORKING_HOURS = "OUTSIDE_WORKING_HOURS"
    BLACKOUT_DATE = "BLACKOUT_DATE"
    OUTSIDE_TERM = "OUTSIDE_TERM"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    NOTICE_DEADLINE_PASSED = "NOTICE_DEADLINE_PASSED"


class BlockReason(StrEnum):
    """Why a slot is not feasible for one member or for the rooms (near-miss reason).

    interfaces.md T02 -> NearMiss.blocked_by. STALE is not a blocker: stale input is
    still usable and is listed in SlotOption.low_confidence_inputs instead.
    """

    NO_REPLY = "NO_REPLY"  # the member has given no availability yet
    UNAVAILABLE = "UNAVAILABLE"  # said unavailable at that time, declined it, or withdrew
    NOT_STATED = "NOT_STATED"  # gave availability, but not for this time
    UNCLEAR = "UNCLEAR"  # covered only by a low-confidence or flagged statement
    CONDITION = "CONDITION"  # available only under a condition that cannot be met here
    NO_ROOM = "NO_ROOM"  # no room fits (capacity, hybrid) and is free


class OutputProblemCode(StrEnum):
    """Why an outbound text was blocked by the output validator (FM-21, TH-02)."""

    TOO_LONG = "TOO_LONG"
    EMPTY = "EMPTY"
    OTHER_MEMBER_ALIAS = "OTHER_MEMBER_ALIAS"
    PROTECTED_TERM = "PROTECTED_TERM"  # another member's name, a private reason, or a canary
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    URL = "URL"
    AMBIGUOUS_NUMERIC_DATE = "AMBIGUOUS_NUMERIC_DATE"  # "3/11": 3 Nov or 11 Mar?
    INVALID_DATE = "INVALID_DATE"  # "31 Nov"
    DATE_OUTSIDE_WINDOW = "DATE_OUTSIDE_WINDOW"
    WEEKDAY_DATE_MISMATCH = "WEEKDAY_DATE_MISMATCH"
