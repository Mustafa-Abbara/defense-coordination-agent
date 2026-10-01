# Data Model

Related documents: `architecture.md` (ADR-006 memory, ADR-013 pseudonyms), `state_machine.md` (status values), `interfaces.md` (schemas used by tools), `threat_model.md`.

All times are stored in **UTC** as ISO-8601 strings. Each member has a display time zone (IANA name, for example `Asia/Beirut`). Conversion happens only in the resolver and in the UI and email templates.

## Entities

Entities from the brief that were **merged or dropped**:

- **Role** → an enum field on `CommitteeMember`. Role *rules* live in `PolicyConfig`. A separate table adds nothing.
- **CandidateSlot** → not stored as its own table. The solver computes slots on demand. A slot is saved only inside an `ApprovalRequest` payload and in traces.
- **AgentAction** and **AuditRecord** → merged. Every state change and security-relevant action is a `WorkflowEvent` in one append-only, hash-chained log. LLM and tool calls are `TraceSpan`s.
- **Timer** → added. Reminders, deferrals, and deadlines need durable timers.
- **User** → added. It is needed for login and role checks.

### Defense

| Field | Type | Notes |
|---|---|---|
| id | str (UUID4, stdlib `uuid`) | |
| owner_user_id | FK → User | The student |
| title | str | Public once announced |
| degree_level | enum `MSC`, `PHD` | Selects duration and role rules in PolicyConfig |
| window_start, window_end | date | Chosen by the student; checked against term dates. Read in the university zone (`policy.timezone`) |
| attendance_mode | enum `IN_PERSON`, `HYBRID_ALLOWED`, `HYBRID_REQUIRED` | Can change later (the chair changes requirements) |
| expected_audience | int | For room capacity |
| status | enum (see `state_machine.md`) | |
| state_version | int | Increases on every save; used for optimistic locking and approval staleness |
| policy_version | str (sha256 of the canonical JSON of the validated `policy.yaml` values) | Frozen at start; shown in approvals. Hashing the values, not the file bytes, means comments and CRLF/LF line endings do not change it; any changed value does |
| scheduled_slot | Slot? | Set when approved |
| previous_status | enum? | The status saved on entering `ESCALATED`; `RESUME` returns to it (`state_machine.md`). Never `ESCALATED` itself |
| agent_paused | bool | Manual override (FR-23) |
| budget_spent_usd, tokens_in, tokens_out | float, int | Running totals |
| created_at, updated_at | datetime | Simulated clock time |

### CommitteeMember

| Field | Type | Notes |
|---|---|---|
| id | str | |
| defense_id | FK → Defense | |
| alias | str `M1`…`M7` | Pseudonym used in planner context (ADR-013) |
| full_name, email | str | **PII.** Never sent to the planner LLM |
| role | enum `ADVISOR`, `CO_ADVISOR`, `CHAIR`, `INTERNAL`, `EXTERNAL` | Values are ASSUMPTION A-04 |
| is_mandatory | bool | Computed from policy and role, can be set by the student; shown on the board |
| timezone | str (IANA) | |
| attendance | enum `IN_PERSON`, `REMOTE_OK`, `REMOTE_ONLY` | From setup, updated by replies |
| calendar_opt_in | bool | FR-11 |
| status | enum member status (see `state_machine.md`) | |
| messages_sent, reminders_sent, clarifications_sent | int | For rate limits and metric M-06 |
| last_contacted_at, last_replied_at | datetime? | |
| recheck_at | datetime? | Set by deferral |

### AvailabilityStatement

One statement = one piece of meaning from one message. A reply can produce several statements.

| Field | Type | Notes |
|---|---|---|
| id | str | |
| member_id | FK | |
| source_message_id | FK → Message? | Null when entered by hand (then `source = MANUAL`) |
| source | enum `EMAIL`, `MANUAL`, `CALENDAR` | |
| kind | enum `AVAILABLE`, `UNAVAILABLE`, `CONDITIONAL`, `DEFERRAL`, `WITHDRAWAL`, `CONFIRM`, `DECLINE` | |
| raw_expression | str | The extractor's structured phrase, for example `{"day":"TUE","part":"AFTERNOON"}` |
| intervals_utc | list[[start, end]] | Filled by the **resolver**, not the LLM |
| condition | enum? `HYBRID_REQUIRED`, `REMOTE_ONLY`, `IF_MEMBER_PRESENT`, `OTHER` | |
| private_reason | str? | **Restricted.** For example "teaching". Visible only to the owner student (see the visibility table) |
| confidence | float 0–1 | From the extractor, lowered by deterministic checks |
| issues | list[IssueCode] | `AMBIGUOUS_DAY`, `AMBIGUOUS_WEEK`, `WEEKDAY_DATE_MISMATCH`, `OUT_OF_WINDOW`, `CONTRADICTS_PREVIOUS`, `CONDITION_UNCLEAR`, `TZ_UNCLEAR`, `UNPARSEABLE`, `SUSPICIOUS_INSTRUCTION`, `TRUNCATED` |
| status | enum `ACTIVE`, `SUPERSEDED`, `RETRACTED`, `NEEDS_REVIEW` | |
| supersedes_id | FK? | |
| observed_at | datetime | Simulated time the statement was received; used for staleness |
| extractor_version | str | Prompt and model version, for reproducibility |

### PolicyConfig (file `config/policy.yaml`, versioned by hash)

**Every value below is a placeholder marked ASSUMPTION. None of them is a university rule.** Replace each with a DOCUMENTED value after source collection (`problem.md` → S1–S4).

```yaml
policy_id: "placeholder-v1"
status: "ASSUMPTION — no source collected yet"
timezone: "Asia/Beirut"            # A-21 — the university's zone; working hours, term, window, notice are read in it
term_windows:                      # A-06 — replace with the academic calendar (S1)
  - {start: "2026-09-01", end: "2026-12-20"}
blackout_dates: []                 # A-06 — holidays, exam periods
notice_days: 14                    # A-05 — days between announcement and defense
duration_minutes: {MSC: 90, PHD: 120}   # A-07
buffer_minutes: 15                 # ASSUMPTION — room setup before and after
working_hours: {start: "08:00", end: "18:00", weekdays: [MON, TUE, WED, THU, FRI]}  # A-19
required_roles:                    # A-04
  MSC: [ADVISOR, INTERNAL]
  PHD: [ADVISOR, CHAIR, INTERNAL, EXTERNAL]
min_committee_size: {MSC: 3, PHD: 5}      # A-02
remote_allowed_roles: [EXTERNAL]   # A-10
max_remote_members: 1              # A-10
substitute_requires_approval_by: [ADVISOR, COORDINATOR]   # A-11 (outside the system)
part_of_day:                       # A-20
  MORNING: ["08:00", "12:00"]
  AFTERNOON: ["13:00", "17:00"]
  EVENING: null                    # outside working hours → flag OUT_OF_WINDOW
```

`config/reminders.yaml` is also a placeholder (ASSUMPTION): first reminder after 3 days, second after 3 more, then `NON_RESPONSIVE`. At most 1 clarification per member per 2 days. At most 6 messages to one member for each defense.

The file is checked by `app/core/config.py` → `PolicyConfig` when it is loaded (ST-02; `timezone` added in ST-03, it must be an exact IANA name): every degree level must have a duration, required roles, and a minimum committee size (at most 7, because aliases are `M1`–`M7`); `part_of_day` must list `MORNING`, `AFTERNOON`, and `EVENING` (`null` disables one); every start is before its end. A missing field, an unknown field, a duplicate key, or an unsafe YAML tag stops loading with a message that names the file and the field.

### Other configuration (ST-02)

`config/reminders.yaml` (`ReminderConfig`, every value ASSUMPTION):

```yaml
first_reminder_after_days: 3          # after the poll, without a reply
next_reminder_after_days: 3           # between reminders
max_reminders: 2                      # then member -> NON_RESPONSIVE
confirmation_reminder_after_days: 2   # in CONFIRMING
clarification_min_gap_days: 2         # at most 1 clarification per member per 2 days
max_messages_per_member: 6            # per member, per defense
```

`config/solver.yaml` (`SolverConfig`, ST-03, every value ASSUMPTION). These are system tuning values, not university rules, so they are not in `policy.yaml` and do not change the policy version:

```yaml
confidence_threshold: 0.7   # an AVAILABLE/CONDITIONAL statement counts only at or above this
staleness_days: 10          # older statements are flagged stale (see Memory below)
grid_minutes: 15            # slot start times every 15 minutes; must divide 60
```

`config/models.yaml` (`ModelsConfig`): `provider`, and for each call kind (`extractor`, `planner`): `model`, `timeout_seconds`, `max_retries`, `temperature`, `price_in_usd_per_million_tokens`, `price_out_usd_per_million_tokens`. Provider, models, and prices are not decided (ADR-008); ST-06 fills them in.

`.env` (`Settings`, via pydantic-settings; names listed in `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `dev` | `dev`, `test`, or `prod` |
| `DEMO_MODE` | `false` | Simulation controls exist only when `true` (TH-05) |
| `LLM_API_KEY` | none | Secret (`SecretStr`); never printed (TH-08) |
| `CONFIG_DIR` | `config` | Folder with the three YAML files |

An unknown variable in `.env` is an error, so a misspelled name cannot be silently ignored.

### Slot

A time interval: `start`, `end` (UTC, `end` after `start`). Used by `Defense.scheduled_slot`. The solver's `SlotOption` (`interfaces.md`, T02) adds its own fields around the same interval.

### Room and Booking

| Room field | Type | | Booking field | Type |
|---|---|---|---|---|
| id | str | | id | str |
| name, building | str | | defense_id | FK |
| capacity | int | | room_id | FK |
| hybrid_capable | bool | | slot_start_utc, slot_end_utc | datetime |
| | | | status | enum `REQUESTED`, `CONFIRMED`, `REJECTED`, `CANCELLED`, `LOST` |
| | | | external_ref | str (mock service ID) |
| | | | idempotency_key | str (`defense_id:approval_id:book`) |

Rooms come from a mock catalogue (`eval/fixtures/rooms.yaml`), which is synthetic.

### Message

| Field | Type | Notes |
|---|---|---|
| id | str | |
| defense_id, member_id | FK? | Null if unmatched |
| direction | enum `IN`, `OUT` | |
| provider_message_id | str | Used for deduplication |
| content_hash | str | sha256 of the normalized body; second dedupe key |
| thread_token | str? | For example `[DEF-7Q2K]` in the subject; used for matching. Null when an inbound message had no valid token (it is quarantined, ADR-014) |
| from_addr, to_addrs | str | PII |
| subject | str | |
| body_raw | str | **Restricted.** Inbound: the raw email. Outbound: the rendered text |
| body_redacted | str | For logs and traces |
| sender_verified | bool | Mock "authentication passed" flag plus an address match |
| processing_status | enum `NEW`, `EXTRACTED`, `NEEDS_REVIEW`, `QUARANTINED`, `DUPLICATE`, `IGNORED` | |
| purpose | enum (OUT only) `POLL`, `REMINDER`, `CLARIFICATION`, `INVITE`, `ANNOUNCEMENT`, `SUBSTITUTE_REQUEST`, `CANCEL` | |
| structured_meta | JSON (OUT only) | The slots or issues asked about. Personas read this (ADR-011) |
| template_id | str (OUT only) | |
| created_by | str | Tool call ID or `executor:<approval_id>` |

### ApprovalRequest

| Field | Type | Notes |
|---|---|---|
| id | str | |
| defense_id | FK | |
| action_type | enum `START_POLL`, `SCHEDULE` (book + invite), `ANNOUNCE`, `REPOLL`, `SUBSTITUTE_REQUEST`, `RESCHEDULE`, `CANCEL` | |
| payload | JSON | The exact action: slot, room, recipients (IDs), rendered message texts |
| payload_hash | str | sha256 of the canonical JSON |
| state_version | int | The Defense version when the request was created |
| risk_tier | enum `R2` | See `approval_policy.md` |
| agent_rationale | str (at most 500 characters) | Shown to the student |
| validator_report | JSON | Results of all checks when the request was created |
| status | enum `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `STALE`, `EXECUTED`, `FAILED` | |
| decided_by, decided_at, decision_note | | |
| expires_at | datetime | Placeholder: 48 simulated hours |

### Timer

| Field | Type | Notes |
|---|---|---|
| id, defense_id, member_id? | | |
| kind | enum `REMINDER`, `RECHECK`, `RESPONSE_DEADLINE`, `APPROVAL_EXPIRY`, `NOTICE_DEADLINE`, `WINDOW_END`, `AGENT_WAKEUP` | |
| fire_at | datetime | |
| status | enum `PENDING`, `FIRED`, `CANCELLED` | |

### WorkflowEvent (event log and audit record)

| Field | Type | Notes |
|---|---|---|
| seq | int | Increasing per defense |
| defense_id | FK | |
| type | str | For example `MESSAGE_RECEIVED`, `STATEMENT_ADDED`, `STATUS_CHANGED`, `TOOL_CALLED`, `TOOL_REJECTED`, `APPROVAL_DECIDED`, `AUTH_DENIED`, `QUARANTINED` |
| actor | str | `user:<id>`, `agent`, `executor`, `system`, `sim` |
| payload_redacted | JSON | Never contains raw bodies or private reasons |
| sim_time, wall_time | datetime | |
| causation_id | str | The event or tool call that caused this one |
| prev_hash, hash | str | `hash = sha256(prev_hash + canonical(row))`. Makes tampering visible (threat TH-06) |

### TraceSpan (observability)

`run_id` (one agent wake-up or one pipeline run), `span_id`, `parent_id`, `kind` (`LLM`, `TOOL`, `HANDLER`, `VALIDATION`), `name`, `start`, `end`, `latency_ms`, `model`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_usd`, `retries`, `outcome` (`OK`, `ERROR`, `REJECTED`, `TIMEOUT`), `error_code`, `attributes_redacted`.

### User

`id`, `display_name`, `role` (`STUDENT`, `OBSERVER`, `ADMIN`), `password_hash` (argon2, via `argon2-cffi`), `api_token_hash`. The agent runs as the service identity `agent`. That identity cannot log in and cannot call approval endpoints.

## Relationships

```text
User 1───* Defense 1───* CommitteeMember 1───* AvailabilityStatement *───0..1 Message
                 │                  └──────────* Message
                 ├──* ApprovalRequest ──0..1 Booking *───1 Room
                 ├──* Timer
                 ├──* WorkflowEvent (hash chain)
                 └──* TraceSpan
PolicyConfig (file, hash) ── referenced by Defense.policy_version and ApprovalRequest.validator_report
```

---

## Who can see what

| Data | Owner student | Observer (advisor or coordinator view) | Other committee members (via email) | Planner LLM | Extractor LLM | Logs / traces |
|---|---|---|---|---|---|---|
| Member name, email | yes | yes | only in the final invite recipient list, if policy allows (ASSUMPTION; default **BCC**) | no (alias only) | the sender's own name only | redacted to alias |
| Member's availability intervals | yes | summary only ("available / unavailable / pending") | **no** | yes (by alias) | no | yes (by alias) |
| Private reason ("teaching 2–4") | yes | **no** → "unavailable 14:00–16:00" | **no** | **no** | produces it | **no** (removed) |
| Raw inbound email | yes (message viewer) | no | no | **no** | yes (that one email only) | no; `body_redacted` only |
| Conditions (hybrid required) | yes | yes | only if it changes the invite (for example "hybrid link attached") | yes | produces it | yes |
| Calendar free/busy | busy blocks only | no | no | as intervals, by alias | no | no |
| Final slot and room | yes | yes | yes (invite) | yes | no | yes |
| Budget and traces | yes | no | no | remaining budget only | no | yes |

---

## PII, retention, and redaction

**What counts as PII here:** names, email addresses, raw email bodies, private reasons, travel or location details, calendar free/busy, the student's thesis title (before announcement), IP addresses in server logs.
Members may give sensitive reasons without being asked (for example "medical appointment" or "family matter"). These reasons are stored only in the restricted `private_reason` field. They are never analyzed, categorized, or shown to anyone except the owner student. The system does not ask for reasons. This keeps it clearly outside healthcare: it never processes health information for any purpose.
Synthetic evaluation data contains *fake* PII so the redaction tests are meaningful.

**Redaction rules** (a module in `observability/redaction.py`, applied before anything is written to a log or trace):

1. Emails → `<email:M3>`. Names → alias.
2. Fields named `body_raw`, `private_reason`, `api_key`, `password*`, `authorization` are never logged.
3. Free text in trace attributes is cut to 200 characters after steps 1–2.
4. LLM prompts are stored in traces **only** in the redacted form. The extractor prompt stores a hash of the email body, not the body.
5. A test scans all log and trace output of the evaluation for canary strings and real-looking emails (SEC-06).

**Retention** (ASSUMPTION; set in config):

| Data | Kept for |
|---|---|
| `body_raw`, `private_reason` | Until the defense is `COMPLETED` or `CANCELLED`, plus 30 days. Then overwritten with null. |
| Availability intervals | Same as above |
| Event log, approvals, bookings | Kept (audit). They contain no raw bodies. |
| Traces | 90 days, redacted |
| Evaluation data | Kept (synthetic) |

---

## Memory

**Memory in this system is the structured workflow state.** Nothing else.
There is no conversation history passed between wake-ups, no vector database, and no "long-term memory" of past defenses.

| Aspect | Design |
|---|---|
| **Scope** | One defense. The agent never sees data from another defense. |
| **Lifetime** | From `DRAFT` until retention cleanup after `COMPLETED` or `CANCELLED`. Between wake-ups, the planner keeps **nothing** in its head. Every wake-up starts from the stored state. |
| **What is stored** | Members and statuses, active availability statements, open issues, timers, approvals, bookings, message counters, the last N events. |
| **Retrieval** | Deterministic `build_snapshot(defense)`. It creates a compact JSON (target under 3,000 tokens): defense summary, members by alias with status and a summary of active statements and open issues, the solver's top 5 feasible slots and top 5 near-misses, pending approvals, next timers, last 10 events, remaining budget, and the tools allowed in the current state. No similarity search is needed, because the state is small and fully structured. |
| **Update rules** | Only deterministic handlers and tool executors write state. The agent cannot write fields directly; it can only call tools. Each save checks `state_version` (optimistic lock). Each change appends a `WorkflowEvent`. |
| **Superseding** | A newer statement from the same member replaces older statements that overlap in time, **if** the newer one clearly corrects them ("sorry, I have a conflict after all"). If it conflicts without a clear correction, both are kept, marked `CONTRADICTS_PREVIOUS`, and a clarification is suggested. |
| **Stale information** | Each statement has `observed_at`. A statement older than `staleness_days` (`config/solver.yaml`, placeholder: 10 simulated days) when a schedule is proposed is marked stale in the snapshot. Stale statements are re-confirmed in the invite step: the invite asks each member to confirm. A `DEFERRAL` statement expires at its `recheck_at`. A room availability result is never cached; it is re-checked just before booking. |
| **Privacy** | Aliases only in the planner. Private reasons are never in the snapshot. See the visibility table above. |
