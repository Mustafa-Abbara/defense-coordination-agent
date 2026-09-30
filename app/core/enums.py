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
