# State Machine

Related documents: `data_model.md` (Defense.status, CommitteeMember.status, Timer), `interfaces.md` (tools T01–T11), `approval_policy.md` (tiers R0–R3), `failure_matrix.md` (FM-xx).

There are two state machines:

1. **Defense state machine.** The workflow as a whole. The code enforces it: a transition not in the table raises an error and is logged.
2. **Member state machine.** One per committee member. It records where each conversation stands.

The agent never sets a state directly. States change only through deterministic handlers, tool executors, and human decisions.

---

## Defense states

| State | Meaning | Kind |
|---|---|---|
| `DRAFT` | The student is setting up the defense. Nothing has been sent. | start |
| `COLLECTING` | Availability requests are out. Replies are interpreted. The agent clarifies, reminds, and waits. | active |
| `AWAITING_APPROVAL` | The agent proposed a schedule. It waits for the student's decision. | active |
| `BOOKING` | Approved. The executor is requesting the room and will send invites. | transient |
| `CONFIRMING` | Room confirmed, invites sent. Waiting for members to confirm. | active |
| `SCHEDULED` | Room confirmed and all mandatory members confirmed. The announcement is prepared or sent. | active |
| `RESCHEDULING` | A disruption happened after proposing or scheduling. The agent chooses a recovery strategy. | active |
| `ESCALATED` | A human must act. The agent is paused (read-only tools only). | waiting |
| `COMPLETED` | The simulated clock passed the end of the defense. | terminal |
| `CANCELLED` | The student cancelled. | terminal |
| `FAILED` | The system stopped safely and cannot continue (see exit conditions). | terminal |

### Diagram

```text
                 start (student, approval R2: START_POLL)
   ┌───────┐  ─────────────────────────────────────────▶ ┌─────────────┐
   │ DRAFT │                                              │ COLLECTING  │◀───────────────┐
   └───────┘                                              └──┬───┬───▲──┘                │
                                  propose_schedule (T07)      │   │   │ reject / expire /   │
                                  ┌───────────────────────────┘   │   │ stale               │
                                  ▼                               │   │                     │
                        ┌───────────────────┐   approve           │   │                     │
                        │ AWAITING_APPROVAL │───────────┐         │   │                     │
                        └─────────┬─────────┘           ▼         │   │                     │
                                  │            ┌──────────┐  room rejected                  │
                                  │            │ BOOKING  │───────┘   │                     │
                                  │            └────┬─────┘           │                     │
                                  │  room confirmed + invites sent    │                     │
                                  │                 ▼                 │                     │
                                  │         ┌─────────────┐  decline / cancel               │
                                  │         │ CONFIRMING  │──────────────────┐              │
                                  │         └──────┬──────┘                  ▼              │
                                  │  all mandatory confirmed        ┌────────────────┐      │
                                  │                ▼                │ RESCHEDULING   │──────┘
                                  │         ┌─────────────┐ disrupt │ (agent picks   │ re-collect
                                  │         │ SCHEDULED   │────────▶│  strategy)     │
                                  │         └──────┬──────┘         └───────┬────────┘
                                  │   clock > defense end                   │ new proposal
                                  │                ▼                        ▼
                                  │         ┌─────────────┐        AWAITING_APPROVAL
                                  │         │ COMPLETED   │
                                  │         └─────────────┘
   any active state ── escalate (agent or D trigger) ──▶ ESCALATED ── student resolves ──▶ previous state
   any non-terminal ── student cancels (R2: CANCEL) ──▶ CANCELLED
   ESCALATED ── unresolved past window end, or integrity failure ──▶ FAILED
```

### State details

#### DRAFT

- **Entry:** the student creates a defense (FR-01).
- **Allowed actions:** the student edits the setup. There is no agent and no sending.
- **Deterministic checks:** policy validation (FR-02): required roles present, committee size, window inside term dates, `window_end − now ≥ notice_days`, time zones valid, emails well-formed and unique.
- **Approval:** "Start coordination" shows the poll preview. Clicking it is the approval `START_POLL`.
- **Exit:** → `COLLECTING` when the checks pass and the student approves. The poll is sent to all members.
- **Failure:** checks fail → stay in `DRAFT` with errors shown. Email send fails → FM-09 (stay in `DRAFT`, retry later).

#### COLLECTING

- **Entry:** poll sent; or coming back from `AWAITING_APPROVAL` (reject, expire, stale), `BOOKING` (room rejected), `RESCHEDULING` (re-collect), `ESCALATED` (resume).
- **Allowed tools:** T01 snapshot, T02 find slots, T03 check rooms, T04 clarification, T05 reminder, T06 request availability (single member R1; re-poll of everyone needs R2), T07 propose schedule, T08 propose substitute, T10 escalate, T11 wait.
- **Deterministic handlers (no agent):** inbound pipeline, statement resolution, reminder timers, deferral rechecks, the `NON_RESPONSIVE` mark after the last reminder, and notice-deadline timers (a slot drops out when its notice deadline passes).
- **When the agent is woken:** a new statement with issues; a member becomes `NON_RESPONSIVE`, `WITHDRAWN`, or replies after a clarification; the feasible set changes (grows from 0, shrinks to 0, or the best slot expires in less than 2 days); an approval is rejected, expires, or goes stale; an `AGENT_WAKEUP` timer the agent set itself.
- **Exit conditions:**
  - T07 creates an approval → `AWAITING_APPROVAL`.
  - T10, or a D trigger (budget exhausted, step budget exceeded twice in a row, window exhausted: no feasible slot can exist any more) → `ESCALATED`.
- **Approval needed:** T06 re-poll of everyone, T07, T08.
- **Failure transitions:** LLM errors (FM-10 to FM-13) → retry, then fall back: extraction → review queue; planner → escalate after 3 failed wake-ups in a row.

#### AWAITING_APPROVAL

- **Entry:** T07 created a `SCHEDULE` approval request.
- **Allowed:** inbound processing continues. The agent is woken only if a new event makes the pending request **stale**: the validator re-runs on every state change and checks whether the slot is still feasible.
- **Deterministic checks:** on approval, the executor verifies the payload hash, the state version, the current feasibility, and room availability.
- **Exit:** approve → `BOOKING`. Reject (with the student's note, which is passed to the agent) → `COLLECTING`. Expiry (placeholder: 48 simulated hours) → `COLLECTING`. Stale → `COLLECTING`, and the agent is told why.
- **Failure:** approval of a stale request is refused (FM-17). The UI says "state changed, please review the new proposal."

#### BOOKING (transient; no agent)

- **Entry:** `SCHEDULE` approved.
- **Actions (executor, in order, each with an idempotency key):** 1) request the room; 2) wait for the room decision (the mock can answer immediately or after a delay); 3) when confirmed, send invites asking each member to confirm.
- **Exit:** room confirmed and invites sent → `CONFIRMING`. Room rejected → `COLLECTING` (agent woken with reason `ROOM_REJECTED`; the near-miss info includes other rooms).
- **Failure:** the room service is down → retry with backoff (3 tries), then `ESCALATED` (FM-06, FM-09). A crash between steps → on restart, the executor sees the finished steps by their idempotency keys and continues (FM-18).

#### CONFIRMING

- **Entry:** invites sent.
- **Allowed tools:** T01, T04 (clarify a confirmation, for example "only if hybrid"), T05, T09 propose reschedule, T10, T11.
- **Deterministic:** confirmation parsing uses the same pipeline (statement kinds `CONFIRM` and `DECLINE`). A confirmation reminder is sent after the placeholder of 2 days.
- **Exit:** all mandatory members `CONFIRMED` → `SCHEDULED`, and the handler automatically creates the `ANNOUNCE` approval from a template. A mandatory member declines, or a condition cannot be met → `RESCHEDULING`. An optional member declines → stay, the agent is informed, and the invite is updated.
- **Failure:** the notice deadline for the slot passes before all confirm → `RESCHEDULING` with reason `NOTICE_DEADLINE_MISSED`.

#### SCHEDULED

- **Entry:** all mandatory members confirmed and the room is confirmed.
- **Allowed:** `ANNOUNCE` approval is pending or done. Inbound processing continues. Tools: T01, T04, T09, T10, T11.
- **Deterministic checks before the announcement is sent:** `slot_start − now ≥ notice_days`. If not → the announcement is blocked and the defense goes to `ESCALATED` (it must not be announced late, A-05).
- **Exit:** clock passes the defense end → `COMPLETED`. A disruption (member cancels, room `LOST`, the chair changes the attendance mode so the room no longer fits) → `RESCHEDULING`.

#### RESCHEDULING

- **Entry:** a disruption in `CONFIRMING` or `SCHEDULED`.
- **This is where the agent adds the most value.** Allowed tools: T01, T02 (including near-misses), T03, T04, T06, T07, T08, T09, T10, T11.
  The agent chooses a strategy, for example:
  - Same slot, new room (room lost).
  - Same slot, ask the cancelling member whether remote attendance is possible (if policy allows).
  - A near-miss slot: ask only the one member who blocks it.
  - Propose a substitute (non-mandatory member, or policy allows).
  - Re-poll everyone (last resort; needs approval).
- **Deterministic:** existing bookings and invites stay until a `RESCHEDULE` approval cancels them. The system never cancels a public announcement by itself.
- **Approval:** `RESCHEDULE` (cancel old booking and invites, and send a notice) and any new `SCHEDULE`.
- **Exit:** new proposal → `AWAITING_APPROVAL`. Need more replies → `COLLECTING`. Stuck → `ESCALATED`.

#### ESCALATED

- **Entry:** T10, or deterministic triggers: `BUDGET`, `STEP_BUDGET`, `WINDOW_EXHAUSTED`, `REPEATED_TOOL_FAILURE`, `LLM_UNAVAILABLE`, `SECURITY` (possible injection or spoofing on a mandatory member's thread), `ANNOUNCEMENT_TOO_LATE`.
- **Allowed:** the student edits data, enters availability by hand, extends the window, releases or rejects quarantined messages, resumes, or cancels. The agent is paused. Inbound messages are still stored and extracted.
- **Exit:** student resumes → the state saved at entry (`previous_status`). Student cancels → `CANCELLED`. No human action and the window end passes → `FAILED` (reason `WINDOW_PASSED`). The event log hash chain is broken → `FAILED` (reason `INTEGRITY`).

#### COMPLETED, CANCELLED, FAILED

- Terminal. Only read-only views are allowed. Retention timers start (see `data_model.md`).
- `CANCELLED` sends cancellation notices only through an approved `CANCEL` request.

### Allowed tools per state (least privilege)

| Tool | COLLECTING | AWAITING_APPROVAL | CONFIRMING | SCHEDULED | RESCHEDULING | ESCALATED |
|---|---|---|---|---|---|---|
| T01 get_workflow_snapshot | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| T02 find_candidate_slots | ✓ | ✓ | – | – | ✓ | – |
| T03 check_rooms | ✓ | – | – | – | ✓ | – |
| T04 send_clarification | ✓ | ✓ | ✓ | ✓ | ✓ | – |
| T05 send_reminder | ✓ | – | ✓ | – | ✓ | – |
| T06 request_availability | ✓ | – | – | – | ✓ | – |
| T07 propose_schedule | ✓ | – | – | – | ✓ | – |
| T08 propose_substitute | ✓ | – | – | – | ✓ | – |
| T09 propose_reschedule | – | – | ✓ | ✓ | ✓ | – |
| T10 escalate_to_human | ✓ | ✓ | ✓ | ✓ | ✓ | – |
| T11 wait | ✓ | ✓ | ✓ | ✓ | ✓ | – |

The planner receives **only** the tools allowed in the current state. The validator checks the state again, in case the state changed during the wake-up.

---

## Member states

```text
NOT_CONTACTED ─poll sent─▶ AWAITING_REPLY ─reply ok─▶ REPLIED ─invite─▶ INVITED ─confirm─▶ CONFIRMED
                              │   ▲                       │                 │
                reminders max │   │ reply                 │ issues          └─decline─▶ DECLINED
                              ▼   │                       ▼
                        NON_RESPONSIVE        NEEDS_CLARIFICATION ─T04─▶ CLARIFICATION_SENT ─reply─▶ REPLIED
   any ── "ask me next week" ──▶ DEFERRED ── recheck timer ──▶ AWAITING_REPLY
   any ── "I must withdraw" ──▶ WITHDRAWN (agent woken; T08 may follow)
   CONFIRMED ── "conflict after all" ──▶ DECLINED (defense → RESCHEDULING if mandatory)
```

Rules:

- A late reply from a `NON_RESPONSIVE` member is still processed. The member goes back to `REPLIED` or `NEEDS_CLARIFICATION`.
- No reminders are sent to `DEFERRED` members before `recheck_at`.
- Message limits (see `approval_policy.md`) apply in every member state.

---

## Simulated clock

### Interface

```python
class Clock(Protocol):
    def now(self) -> datetime: ...          # always UTC, timezone-aware

class SimClock(Clock):
    def advance(self, delta: timedelta) -> list[Event]: ...
    def advance_to(self, t: datetime) -> list[Event]: ...
    def run_until_idle(self, max_sim_time: datetime) -> list[Event]: ...
```

### How time advances

1. Everything that will happen in the future is a scheduled item in one priority queue: timers (reminders, rechecks, deadlines, approval expiry), **persona replies** (the persona simulator schedules each reply at `sent_time + its sampled delay`), room decisions from the mock, and fault windows (for example "email down from day 3 09:00 to day 3 15:00").
2. `advance(2 days)` pops every item with `fire_at ≤ now + 2 days` in order. Ties are ordered by `(fire_at, priority, sequence number)`, so order is always the same. The clock is set to each item's time **before** the item is processed. An agent wake-up at day 1 10:00 therefore sees day 1 10:00 as "now". It can schedule new items, and they are handled within the same `advance` call if they fall inside the range.
3. The agent's own LLM latency does **not** move simulated time. Wall-clock time is measured separately for latency metrics (M-09).
4. Only `SystemClock` (used in real deployment) follows real time. Code never calls `datetime.now()` directly (lint check, ADR-010).

### In tests

```python
clock = SimClock(start=datetime(2026, 11, 2, 8, 0, tzinfo=UTC))
world = build_world(scenario="S09", seed=3, clock=clock)
world.start_defense()
clock.advance(timedelta(days=3))       # first reminder fires
assert world.member("M4").reminders_sent == 1
clock.run_until_idle(max_sim_time=clock.now() + timedelta(days=30))
assert world.defense.status in {"SCHEDULED", "ESCALATED"}
```

### In the demo (dashboard, dev/demo mode only)

Buttons: **+1 hour**, **+1 day**, **+2 days**, **Run to next event**, and **Inject event** (for example "M3 cancels", "room lost", "email service down 6 h").
The top bar always shows the simulated date and time, and the number of pending timers.
All these controls are behind `DEMO_MODE=true` and need the `ADMIN` role (see `threat_model.md`, TH-05).
