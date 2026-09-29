# Requirements

Related documents: `problem.md` (assumptions A-xx), `architecture.md`, `state_machine.md`, `evaluation.md` (metrics M-xx, scenarios S-xx).

Priority: **MUST** = needed for the December demo. **SHOULD** = planned, can be cut. **COULD** = only if time allows.

## Functional requirements

### Setup

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The student creates a defense with: title, degree level, committee members (name, email, role, time zone, mandatory flag, attendance mode), a date window, and expected audience size. | MUST |
| FR-02 | Before coordination starts, the system checks the setup against PolicyConfig (required roles present, window inside term dates, window long enough for the notice period). It shows every violation next to the field that causes it. | MUST |
| FR-03 | The student previews the first availability request and starts coordination with one click. That click is the approval for sending it. | MUST |

### Collecting availability

| ID | Requirement | Priority |
|---|---|---|
| FR-04 | The system reads inbound replies from the mailbox. It drops duplicates, matches each reply to a defense and a member, and checks that the sender is a registered member. Unknown senders are quarantined. | MUST |
| FR-05 | The system extracts structured availability statements from free text: available or unavailable intervals, conditions (for example, hybrid required), deferrals, withdrawals. Each statement has a confidence value and issue flags. | MUST |
| FR-06 | Relative dates ("next Tuesday"), parts of day ("afternoon"), and time zones are turned into exact times **by code, not by the LLM**. | MUST |
| FR-07 | The system detects ambiguous statements, statements that contradict earlier ones, and statements outside the window. It sends each to clarification or human review. | MUST |
| FR-08 | The agent can send a targeted clarification question to **one** member. The number of messages per member is limited (see `approval_policy.md`). | MUST |
| FR-09 | Routine reminders are sent by deterministic timers according to the reminder policy. After the last reminder, the member is marked `NON_RESPONSIVE` and the agent is woken up. | MUST |
| FR-10 | Deferrals ("ask me again next week") create a recheck timer. The member is not reminded before that time. | MUST |
| FR-11 | Members who opt in can share calendar free/busy (busy blocks only, no event titles). It is used as extra "unavailable" input and is never shown to others. | COULD |

### Planning

| ID | Requirement | Priority |
|---|---|---|
| FR-12 | A deterministic slot solver computes all feasible slots (every hard constraint met) and "near-miss" slots (feasible except for one named member or one missing room). | MUST |
| FR-13 | On every wake-up, the agent chooses its next action from the tools allowed in the current state. It records a short rationale for each tool call. | MUST |
| FR-14 | The system finds rooms that fit a slot: capacity, hybrid equipment if needed, and free at that time. | MUST |
| FR-15 | The agent proposes a schedule (slot, room, invite text) as an approval request. It cannot book or invite by itself. | MUST |

### Execution and changes

| ID | Requirement | Priority |
|---|---|---|
| FR-16 | After approval, a deterministic executor checks everything again, books the room, and sends the invites. Each step has an idempotency key so it is never done twice. | MUST |
| FR-17 | The system tracks each member's confirmation. A decline or cancellation starts re-planning. | MUST |
| FR-18 | When all mandatory members have confirmed and the notice period can be met, the system prepares the announcement from a template for approval. | MUST |
| FR-19 | After scheduling, a member cancellation, a lost room, or a changed requirement (for example, the chair now asks for hybrid) moves the defense to `RESCHEDULING`. | MUST |
| FR-20 | The agent can propose a substitute member. The system only drafts a request to the advisor or coordinator after the student approves. It never changes the committee by itself. | SHOULD |
| FR-21 | The agent (or a deterministic trigger: budget, deadline, repeated errors) escalates to the student with a reason code and a short summary. | MUST |

### Oversight and operations

| ID | Requirement | Priority |
|---|---|---|
| FR-22 | Dashboard (not chat): coordination board, availability grid, approval inbox, review queue, event timeline, trace viewer. Screens and error states are specified in `ui.md`. | MUST |
| FR-23 | Manual override: the student can enter or correct a member's availability, pause and resume the agent, and cancel the defense. | MUST |
| FR-24 | Simulated clock controls and fault injection, in dev and demo mode only (turned off by a config flag). | MUST |
| FR-25 | Every event, LLM call, and tool call is recorded with latency, tokens, cost, and outcome. | MUST |
| FR-26 | An evaluation harness runs scenarios without the UI and writes metric reports (CSV and Markdown). | MUST |
| FR-27 | Baseline runners (B1 fixed-rule workflow, B2 single LLM call; optional B1c rules + clarification) use the same mocks, clock, and scenarios. | MUST (B1c: SHOULD) |

## Non-functional requirements

Values marked "(proposed)" are targets chosen by us. They are not taken from any source.

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | **Safety.** No executed action (booking, invite, announcement) breaks a hard constraint. | 0 violations across all evaluation runs |
| NFR-02 | **Privacy.** No outbound message or observer view contains another member's private reason, email, or availability details. | 0 leaks (canary test, metric M-10) |
| NFR-03 | **Reliability.** After a crash, the system restarts from stored state without duplicate emails or bookings. | 0 duplicates in crash tests |
| NFR-04 | **Observability.** Every agent wake-up has a trace with spans for each LLM and tool call. | 100% of wake-ups traced |
| NFR-05 | **Reproducibility.** One command runs the evaluation suite with fixed seeds. Results come with commit hash, prompt versions, and model names. | `python -m eval.run --suite core` |
| NFR-06 | **Cost control.** A hard spend cap per run and in total. When it is reached, the system degrades (manual review or escalation) and does not crash. | Configurable; default set when the budget is known |
| NFR-07 | **Latency.** Agent wake-up p95 below 30 s. Pages that do not call the LLM load in under 1 s locally. | (proposed) |
| NFR-08 | **Security.** Login for UI and API. Role checks on every endpoint. Secrets only from environment or `.env`, never in git. | Security tests SEC-xx pass |
| NFR-09 | **Maintainability.** Modules separated by responsibility. Type hints. Ruff lint clean. At least 80% test coverage of deterministic modules. | (proposed) |
| NFR-10 | **Portability.** Runs on Windows 10/11 with Python 3.12 and no Docker. Docker is optional. | Setup tested on Windows |
| NFR-11 | **Testability.** Every external service is behind an interface. A scripted `FakeLLM` lets tests run offline for free. | Unit tests use no network |
| NFR-12 | **Low burden on faculty.** Few messages, each short and clear. | Emails per member (M-06), (proposed) median of 3 or fewer per member when there is no disruption |

## Success criteria

The project is successful if the held-out evaluation (see `evaluation.md`) shows:

| ID | Criterion | Target (proposed) | Metric |
|---|---|---|---|
| SC-01 | Hard-constraint violations in executed actions | **0** | M-02 |
| SC-02 | Task success rate of the agent is higher than both baselines, with the difference larger than seed-to-seed variation | Agent above B1 and B2 | M-01 |
| SC-03 | Recovery after disruption (cancellation, room loss, changed requirement) | At least 70% | M-03 |
| SC-04 | Prompt-injection success rate (forbidden effect actually happened) | **0** | M-11 |
| SC-05 | Privacy leaks | **0** | M-10 |
| SC-06 | Human approvals per scheduled defense (no disruption) | 3 or fewer (start, schedule, announcement) | M-07 |
| SC-07 | Cost per successful scenario is reported, with the budget respected | Reported; no overrun | M-08 |
| SC-08 | Extraction accuracy on the labeled reply set (status label) | At least 90% | M-13 |

If a target is not met, the result is still reported. It goes into `risks.md` and the final report. It is not removed.

---

## Real-world constraints

The course requires at least one constraint to be **evaluated**. This project evaluates **C-01, C-02, C-03, C-04**. C-05 and C-06 are handled but only partly measured.

### C-01 Human response latency

- **Why it matters.** Members answer after hours or days, or never. The process lasts weeks while the notice deadline gets closer. This is the main reason the task needs an agent that can wait, observe, and re-plan instead of a single call. (A-13, A-15)
- **Effect on behavior.**
  - The system is event-driven. It sleeps until a reply, a timer, or an approval arrives. No polling LLM loop.
  - Reminder timers follow the reminder policy. Deferrals create recheck timers.
  - The solver removes slots whose notice deadline has passed. The agent sees "slots expiring soon" and can act earlier (for example, propose with the mandatory members only, or escalate).
- **Measurement.** Simulated days to confirm (M-04). Success rate by reply-delay profile (fast, slow, non-responder). Share of scenarios that fail because the window ran out.

### C-02 Human approval burden

- **Why it matters.** If the student must approve every email, the tool saves nothing. If they approve nothing, a bad booking or announcement is possible. (A-17)
- **Effect on behavior.**
  - Risk tiers (`approval_policy.md`): low-risk actions run automatically, consequential ones need approval, some are never allowed.
  - Related actions are bundled. For example, one approval covers "book room R and send invites for slot S".
  - Every approval shows the exact payload and the validator results, so the decision is quick.
- **Measurement.** Approvals per scenario (M-07), student manual actions per scenario (reviews plus escalations handled), approval rejection rate. In the UI: time from approval request to decision.

### C-03 Privacy of faculty calendars and reasons

- **Why it matters.** Members share reasons ("teaching", "travelling", personal matters) and possibly free/busy data. Others must not see these. Data sent to an external LLM provider leaves the university. (A-12)
- **Effect on behavior.**
  - Private reasons are stored in a separate restricted field. Others see only "unavailable 14:00–16:00".
  - The planner LLM sees pseudonyms (M1…M7) and structured availability, never raw email or reasons.
  - Outbound messages pass an output validator: no other member's name, email, reason, or availability.
  - Calendar data is free/busy only and opt-in.
  - This project uses **synthetic data only**. Using real faculty email would need consent and an approved provider (TO BE VALIDATED, source S6).
- **Measurement.** Privacy leak count using canary strings planted in private reasons (M-10). Redaction check on logs and traces (test SEC-06).

### C-04 Cost (LLM tokens)

- **Why it matters.** The budget is not known yet. Evaluation (40 scenarios × several seeds × baselines × ablation) multiplies the cost of every call.
- **Effect on behavior.**
  - Deterministic code does everything it can. The LLM is used only for extraction, planning decisions, and short clarification text.
  - The planner gets a compact state snapshot, not the full history.
  - There is a budget cap per run and in total. When it is reached, the agent escalates and extraction falls back to manual review.
  - Simulated persona replies come from cached files, so the simulator itself costs nothing (see `evaluation.md`).
  - `FakeLLM` is used for all unit tests.
- **Measurement.** Tokens and cost per scenario and per success (M-08). Cost split by component (extractor vs. planner). Cost of the small vs. large model if that comparison is run.

### C-05 LLM API reliability and rate limits (handled, partly measured)

- **Why it matters.** Provider timeouts, rate limits, and malformed outputs happen.
- **Effect on behavior.** Timeouts, retries with backoff, schema validation with one repair attempt, fallback to manual review or escalation. See `failure_matrix.md` FM-10 to FM-13.
- **Measurement.** Retries, tool failures, and agent errors per run. Fault-injection scenarios (S25–S28).

### C-06 Policy uncertainty (handled)

- **Why it matters.** No policy source is collected yet (see `problem.md`).
- **Effect on behavior.** All policy values live in `config/policy.yaml`. Each is marked with its assumption ID. The policy version (hash) is saved with each defense and approval.
- **Measurement.** Not a metric. It is reported as a limitation until sources are collected.
