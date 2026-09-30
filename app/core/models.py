"""Domain models: one class per entity in docs/data_model.md (ST-02).

These classes only describe and check data. They do not load, save, send, or
decide anything. Storage is ST-04; the rules that use these values (policy,
solver, validators) are ST-03.

Privacy: fields marked "PII" or "Restricted" in data_model.md use repr=False,
so printing a model (for example into a log line) does not show them. The full
redaction layer for logs and traces comes in ST-06 (observability/redaction.py).
"""

from datetime import date
from typing import Annotated, Any, Literal, Self

from pydantic import EmailStr, Field, StringConstraints, model_validator

from app.core.enums import (
    ApprovalActionType,
    ApprovalStatus,
    AttendanceMode,
    BookingStatus,
    DefenseStatus,
    DegreeLevel,
    IssueCode,
    MemberAttendance,
    MemberStatus,
    MessageDirection,
    MessagePurpose,
    ProcessingStatus,
    RiskTier,
    Role,
    SpanKind,
    SpanOutcome,
    StatementCondition,
    StatementKind,
    StatementSource,
    StatementStatus,
    TimerKind,
    TimerStatus,
    UserRole,
)
from app.core.fields import (
    EntityId,
    IanaTimeZone,
    MemberAlias,
    Sha256Hex,
    StrictModel,
    UtcDatetime,
)

# A short free-text label, such as a building name or a template id.
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Slot(StrictModel):
    """A time interval for the defense, in UTC. Used by Defense.scheduled_slot."""

    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class Defense(StrictModel):
    """One thesis defense being coordinated. The root of all other records."""

    id: EntityId
    owner_user_id: EntityId  # the student
    title: str = Field(min_length=1, max_length=300)
    degree_level: DegreeLevel
    window_start: date
    window_end: date
    attendance_mode: AttendanceMode
    expected_audience: int = Field(ge=1, le=10_000)  # for room capacity
    status: DefenseStatus = DefenseStatus.DRAFT
    # Increases on every save; optimistic locking and approval staleness (FM-17).
    state_version: int = Field(default=0, ge=0)
    policy_version: Sha256Hex  # frozen at start; shown in approvals
    scheduled_slot: Slot | None = None
    agent_paused: bool = False  # manual override (FR-23)
    # The status saved on entering ESCALATED; RESUME goes back to it.
    previous_status: DefenseStatus | None = None
    budget_spent_usd: float = Field(default=0.0, ge=0)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    created_at: UtcDatetime  # simulated clock time
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def _check_dates_and_previous_status(self) -> Self:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        if self.previous_status is DefenseStatus.ESCALATED:
            # Resuming "back to ESCALATED" would never leave ESCALATED.
            raise ValueError("previous_status cannot be ESCALATED")
        return self


class CommitteeMember(StrictModel):
    """One committee member of one defense."""

    id: EntityId
    defense_id: EntityId
    alias: MemberAlias  # the only name the planner LLM ever sees (ADR-013)
    full_name: str = Field(min_length=1, max_length=120, repr=False)  # PII
    email: EmailStr = Field(repr=False)  # PII
    role: Role
    is_mandatory: bool
    timezone: IanaTimeZone
    attendance: MemberAttendance
    calendar_opt_in: bool = False  # FR-11
    status: MemberStatus = MemberStatus.NOT_CONTACTED
    # Counters for rate limits and metric M-06.
    messages_sent: int = Field(default=0, ge=0)
    reminders_sent: int = Field(default=0, ge=0)
    clarifications_sent: int = Field(default=0, ge=0)
    last_contacted_at: UtcDatetime | None = None
    last_replied_at: UtcDatetime | None = None
    recheck_at: UtcDatetime | None = None  # set by a deferral


# One UTC interval inside a statement: (start, end).
Interval = tuple[UtcDatetime, UtcDatetime]


class AvailabilityStatement(StrictModel):
    """One piece of meaning from one message (a reply can give several)."""

    id: EntityId
    member_id: EntityId
    source_message_id: EntityId | None = None  # None for MANUAL and CALENDAR
    source: StatementSource
    kind: StatementKind
    raw_expression: str = Field(max_length=1000)  # the extractor's structured phrase
    # Filled by the resolver (code), never by the LLM (FR-06).
    intervals_utc: list[Interval] = Field(default_factory=list, max_length=100)
    condition: StatementCondition | None = None
    private_reason: str | None = Field(default=None, max_length=120, repr=False)  # Restricted
    confidence: float = Field(ge=0.0, le=1.0)
    issues: list[IssueCode] = Field(default_factory=list)
    status: StatementStatus = StatementStatus.ACTIVE
    supersedes_id: EntityId | None = None
    observed_at: UtcDatetime  # used for staleness
    extractor_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _check_source_and_intervals(self) -> Self:
        # data_model.md: source_message_id is null exactly when there is no email.
        if self.source is StatementSource.EMAIL and self.source_message_id is None:
            raise ValueError("source_message_id is required when source is EMAIL")
        if self.source is not StatementSource.EMAIL and self.source_message_id is not None:
            raise ValueError("source_message_id must be empty when source is MANUAL or CALENDAR")
        for start, end in self.intervals_utc:
            if end <= start:
                raise ValueError("in intervals_utc, end must be after start")
        return self


class Room(StrictModel):
    """A room from the (synthetic) room catalogue."""

    id: EntityId
    name: ShortText
    building: ShortText
    capacity: int = Field(ge=1)
    hybrid_capable: bool


class Booking(StrictModel):
    """A room request made by the executor after an approval."""

    id: EntityId
    defense_id: EntityId
    room_id: EntityId
    slot_start_utc: UtcDatetime
    slot_end_utc: UtcDatetime
    status: BookingStatus = BookingStatus.REQUESTED
    external_ref: str | None = Field(default=None, max_length=200)  # mock service ID
    idempotency_key: str = Field(min_length=1, max_length=200)  # defense_id:approval_id:book

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.slot_end_utc <= self.slot_start_utc:
            raise ValueError("slot_end_utc must be after slot_start_utc")
        return self


class Message(StrictModel):
    """One email, inbound or outbound."""

    id: EntityId
    defense_id: EntityId | None = None  # None if it could not be matched
    member_id: EntityId | None = None
    direction: MessageDirection
    provider_message_id: str = Field(min_length=1, max_length=300)  # dedupe key
    content_hash: Sha256Hex  # sha256 of the normalized body; second dedupe key
    # For example "[DEF-7Q2K]". None when an inbound message had no valid token
    # (such a message is quarantined, ADR-014).
    thread_token: str | None = Field(default=None, max_length=32)
    from_addr: EmailStr = Field(repr=False)  # PII
    to_addrs: list[EmailStr] = Field(min_length=1, max_length=20, repr=False)  # PII
    subject: str = Field(max_length=300)
    body_raw: str = Field(repr=False)  # Restricted: never logged
    body_redacted: str  # for logs and traces
    sender_verified: bool = False
    processing_status: ProcessingStatus = ProcessingStatus.NEW
    # OUT messages only:
    purpose: MessagePurpose | None = None
    structured_meta: dict[str, Any] | None = None  # what was asked; personas read this
    template_id: str | None = Field(default=None, max_length=100)
    created_by: str = Field(min_length=1, max_length=200)  # tool call id or executor:<id>

    @model_validator(mode="after")
    def _outbound_fields_only_on_outbound(self) -> Self:
        if self.direction is MessageDirection.OUT and self.purpose is None:
            raise ValueError("purpose is required for an outbound (OUT) message")
        if self.direction is MessageDirection.IN:
            has_out_fields = (
                self.purpose is not None
                or self.structured_meta is not None
                or self.template_id is not None
            )
            if has_out_fields:
                raise ValueError(
                    "purpose, structured_meta and template_id are only for OUT messages"
                )
        return self


class ApprovalRequest(StrictModel):
    """An exact action waiting for the student's decision (ADR-009)."""

    id: EntityId
    defense_id: EntityId
    action_type: ApprovalActionType
    payload: dict[str, Any]  # the exact action: slot, room, recipient IDs, rendered texts
    payload_hash: Sha256Hex  # sha256 of the canonical JSON of payload (checked in ST-11)
    state_version: int = Field(ge=0)  # the Defense version when this was created
    # Every approval request is R2 by definition (approval_policy.md).
    risk_tier: Literal[RiskTier.R2] = RiskTier.R2
    agent_rationale: str = Field(max_length=500)
    validator_report: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: EntityId | None = None
    decided_at: UtcDatetime | None = None
    decision_note: str | None = Field(default=None, max_length=1000)
    expires_at: UtcDatetime


class Timer(StrictModel):
    """Something that must happen at a later simulated time."""

    id: EntityId
    defense_id: EntityId
    member_id: EntityId | None = None
    kind: TimerKind
    fire_at: UtcDatetime
    status: TimerStatus = TimerStatus.PENDING


# user:<id>, agent, executor, system, or sim (data_model.md -> WorkflowEvent.actor).
Actor = Annotated[
    str, StringConstraints(pattern=r"^(user:[A-Za-z0-9_-]{1,64}|agent|executor|system|sim)$")
]
EventType = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z_]{0,63}$")]


class WorkflowEvent(StrictModel):
    """One row of the append-only, hash-chained event log (audit record).

    The hash itself is computed by the repository in ST-04:
    hash = sha256(prev_hash + canonical(row)).
    """

    seq: int = Field(ge=1)  # increasing per defense
    defense_id: EntityId
    type: EventType  # for example STATUS_CHANGED, TOOL_REJECTED, AUTH_DENIED
    actor: Actor
    payload_redacted: dict[str, Any]  # never raw bodies or private reasons
    sim_time: UtcDatetime
    wall_time: UtcDatetime
    causation_id: str | None = Field(default=None, max_length=200)
    prev_hash: Sha256Hex
    hash: Sha256Hex


class TraceSpan(StrictModel):
    """One timed step: an LLM call, a tool call, a handler, or a validation."""

    run_id: EntityId  # one agent wake-up or one pipeline run
    span_id: EntityId
    parent_id: EntityId | None = None
    kind: SpanKind
    name: ShortText
    start: UtcDatetime
    end: UtcDatetime
    latency_ms: float = Field(ge=0)
    model: str | None = Field(default=None, max_length=100)
    prompt_version: str | None = Field(default=None, max_length=100)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    retries: int = Field(default=0, ge=0)
    outcome: SpanOutcome
    error_code: str | None = Field(default=None, max_length=64)
    attributes_redacted: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class User(StrictModel):
    """A person who can log in to the dashboard or API."""

    id: EntityId
    display_name: str = Field(min_length=1, max_length=120)
    role: UserRole
    # argon2 hashes (ST-12). None means "cannot log in this way", for example the
    # service identity `agent`, which can never log in.
    password_hash: str | None = Field(default=None, max_length=300, repr=False)
    api_token_hash: str | None = Field(default=None, max_length=300, repr=False)
