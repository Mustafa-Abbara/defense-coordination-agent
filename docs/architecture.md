# Architecture

Related documents: `requirements.md` (FR, NFR, C), `interfaces.md` (tools T01–T11, service interfaces), `state_machine.md`, `approval_policy.md`.

## Summary in one paragraph

One orchestrating LLM agent runs an **event-driven loop**. It wakes up only when something happens: a reply arrives, a timer fires, a room decision comes back, or the student approves or rejects something.
On each wake-up it reads a compact, structured snapshot of the workflow state. It then calls a small set of narrow tools and goes back to sleep.
Everything with a right answer is done by **deterministic code**: date and time math, policy checks, slot feasibility, room fit, permissions, booking, and sending.
Anything consequential needs **student approval**.
The LLM is used in exactly three places:

1. Extracting structured availability from free-text email (no tools, schema-validated).
2. Deciding the next action while the situation is uncertain.
3. Writing the short question text of a clarification.

---

## Decision records

Format: context → decision → consequences. Status is "Accepted" unless marked otherwise.

### ADR-001 One orchestrating agent, no multi-agent design (given)

- **Context.** Solo project. The course says more agents do not mean a better system.
- **Decision.** One planner agent. The email extractor is an LLM *function*, not an agent: it has no tools, no memory, and one input and one output.
- **Consequences.** Simple to trace and defend. All decisions pass through one loop with one tool set.

### ADR-002 Python, and every external system is mocked locally (given)

- **Context.** No access to university systems. The evaluation must be reproducible.
- **Decision.** Python 3.12. Email, calendar free/busy, room booking, policies, committee members (simulated personas), and time (simulated clock) are local mocks behind interfaces. Real Google or university integrations are optional extensions.
- **Consequences.** Full control over faults and timing. The limitation is realism, which is addressed by the grounding plan and the persona design.

### ADR-003 Event-driven wake-ups instead of an always-running agent

- **Context.** The process lasts simulated weeks. A loop that calls the LLM every tick wastes money and is hard to test.
- **Decision.** An `Orchestrator` pulls events from a queue in order: inbound message, timer fired, room decision, approval decision, clock advanced. Deterministic handlers update state first. The agent is woken only for events that need a decision. Each wake-up has a step budget (placeholder: at most 8 tool calls) and ends when the agent calls `wait` (T11).
- **Consequences.** Cost grows with events, not with time. Tests replay event sequences exactly.

### ADR-004 The LLM never owns hard constraints

- **Context.** LLMs make date arithmetic, policy, and capacity mistakes.
- **Decision.** Policy engine, date/time resolver, slot solver, room filter, and validators are plain Python. The agent can only pick from options the solver returns, and every tool call is validated again.
- **Consequences.** Hard-constraint violations should be 0 by construction (SC-01). The evaluation still measures this, because a bug in the validators is possible.

### ADR-005 Extraction is separated from planning (quarantined reader)

- **Context.** Email text is untrusted and may contain prompt injection.
- **Decision.** Raw email goes only to the extractor, which has no tools and must return a fixed JSON schema. The planner never sees raw email. It sees structured statements and issue codes from a fixed list. Raw text is shown only to the student in the UI.
- **Consequences.** An injected instruction can at most produce a wrong *availability statement*. That statement is still range-checked, and the instruction cannot trigger an action (see `threat_model.md`).

### ADR-006 Memory is structured workflow state in SQLite

- **Context.** The agent needs to remember what happened over weeks.
- **Decision.** No chat history and no vector store. State = SQLite tables plus an append-only event log. Each wake-up rebuilds a compact snapshot. Details are in `data_model.md` → Memory.
- **Consequences.** The context size is bounded. Restart after a crash is simple. Behavior is easy to explain.

### ADR-007 FastAPI with a server-rendered dashboard, not chat

- **Context.** The user wants a UI that is not chat. The workflow is a board of people and statuses, with approvals.
- **Decision.** FastAPI serves a JSON API and HTML pages (Jinja2 templates). HTMX is optional for partial page refresh. The CLI and the evaluation harness call the same service layer.
- **Consequences.** A little more work than Streamlit. In return there is a real API with authentication (course requirement: interface contracts) and a UI shaped around the workflow.

### ADR-008 One LLM provider behind an `LLMClient` interface, plus `FakeLLM`

- **Context.** Provider and budget are not decided yet.
- **Decision.** One official provider SDK (**provider: TO BE DECIDED**) wrapped by `LLMClient`. It supports structured output or tool calling, timeouts, retries, token counting, and cost. Model names and prices live in config. `FakeLLM` returns scripted responses for tests.
- **Consequences.** The provider can change in one file. Unit tests are free and deterministic.

### ADR-009 Approvals are hashed payloads, run by a deterministic executor

- **Context.** An approval must cover exactly what will happen, even if the state changes in between.
- **Decision.** The agent creates an `ApprovalRequest` with the exact action payload, its SHA-256 hash, and the state version. After approval, the executor (plain code) checks that the hash matches and runs all validators again on the current state. If the state changed in a relevant way, the request is marked `STALE` and the agent is woken.
- **Consequences.** There is no gap between checking and running an approved action. Approvals can be audited.

### ADR-010 Simulated clock everywhere

- **Context.** Weeks of waiting must run in seconds, and the same way every time.
- **Decision.** All code gets time from a `Clock` interface. Calling `datetime.now()`, `utcnow()` or `today()` directly is banned. Ruff's banned-API rule (TID251) enforces this in lint and CI; only `app/adapters/clock.py` is exempt. `SimClock` advances only when told to. `SystemClock` is for real use.
- **Consequences.** Deterministic tests and a live demo button "advance 2 days".

### ADR-011 Simulated committee: structured ground truth with cached reply text

- **Context.** The evaluation needs reproducible, cheap persona replies. Scoring also needs to know the truth.
- **Decision.** Each persona has hidden **structured** availability and behavior settings (reply delay, vagueness, etc.). Reply text is built from templates, from **LLM paraphrases generated once offline and saved to files**, and from hand-written edge cases. Personas answer the agent's messages using the message's structured metadata, not by reading its text. A live LLM persona mode exists only as an optional stress test. Details are in `evaluation.md`.
- **Consequences.** Evaluation runs cost nothing for the simulator and can be repeated. An oracle knows the true feasible slots. Limitation: this does not test whether real people understand the agent's wording. A manual review of sample messages covers that.

### ADR-012 No Docker by default (Windows)

- **Context.** Development is on Windows. Docker is not confirmed.
- **Decision.** Default setup uses Python venv and pip. A Dockerfile is optional, for the bonus credit and for graders.
- **Consequences.** Needs the `tzdata` package, because Windows has no IANA time zone database for `zoneinfo`.

### ADR-013 Pseudonyms in the planner context

- **Context.** Privacy constraint C-03, and least data sent to the LLM provider.
- **Decision.** The snapshot builder maps members to `M1…Mn` with role and time zone only. Tool arguments use member IDs. Real names are inserted into emails by templates after the LLM step.
- **Consequences.** The planner cannot leak names or emails it never received.

### ADR-014 A dedicated coordination mailbox with least-privilege reading

- **Context.** Replies go to the student. Reading the student's whole inbox would expose unrelated private email to the system and to the LLM provider.
- **Decision.** The system sends from, and reads only, a dedicated coordination address (for a real deployment, a separate mailbox or alias that the student controls). `EmailGateway.fetch_new` returns only messages addressed to that mailbox. Messages without a valid thread token are quarantined and are never sent to the extractor.
- **Consequences.** Least privilege for email (threat TH-13). Faculty see a clear footer explaining that an assistant sends on the student's behalf (A-16). In the mock, this is the only mailbox that exists.

### ADR-015 The interface is designed around the workflow

- **Context.** The course asks for an interface built around the real user and workflow, not chat by default.
- **Decision.** The screens follow the student's tasks: set up, watch the board, approve, review, investigate. Free text appears only where a person really writes (approval notes, manual corrections). Details and the usability check are in `ui.md`.
- **Consequences.** Every screen maps to requirements and states. The design can be tested with real students (task success, time, confusion points).

---

## Component diagram

```text
                        ┌──────────────────────────────────────────────┐
  Student (browser) ───▶│  UI: server-rendered dashboard (Jinja2/HTMX) │
                        └───────────────┬──────────────────────────────┘
                                        │ HTTP (session cookie / bearer token)
                        ┌───────────────▼──────────────────────────────┐
                        │  API layer (FastAPI)                          │
                        │  authn, role checks, request validation       │
                        └───────────────┬──────────────────────────────┘
                                        │ calls
                        ┌───────────────▼──────────────────────────────┐
                        │  Orchestrator (event queue, per-defense lock) │
                        │   ├─ deterministic event handlers             │
                        │   ├─ Inbound pipeline ── LLM Extractor (no     │
                        │   │    tools, JSON schema) ─▶ Resolver ─▶ checks│
                        │   ├─ Agent loop (planner LLM, step budget)    │
                        │   └─ Approved-action Executor (no LLM)        │
                        └──────┬───────────────┬───────────────┬───────┘
                               │ tool calls    │ validate      │ read/write
                ┌──────────────▼───┐   ┌───────▼──────────┐   ┌▼──────────────────┐
                │ Tool layer       │   │ Deterministic    │   │ State repository   │
                │ T01–T11          │──▶│ services         │   │ (SQLite: state,    │
                │ schema + state   │   │ • PolicyEngine   │   │  events hash-chain,│
                │ guard + authz +  │   │ • DateResolver   │   │  approvals, msgs)  │
                │ rate limits      │   │ • SlotSolver     │   └────────────────────┘
                └──────┬───────────┘   │ • RoomFilter     │
                       │               │ • OutputValidator│
                       │               └──────────────────┘
                ┌──────▼─────────────────────────────────────────────┐
                │ Service interfaces (Protocols)                      │
                │ EmailGateway │ CalendarService │ RoomService │ Clock│
                └──────┬─────────────────────────────────────────────┘
                       │ implemented by
                ┌──────▼─────────────────────────────────────────────┐
                │ Mocks: MockMailbox, MockCalendar, MockRoomService, │
                │ SimClock, PersonaSimulator (eval + demo only)      │
                └────────────────────────────────────────────────────┘

  Cross-cutting: Tracer (spans for every LLM call, tool call, handler) → SQLite traces + JSONL export
                 Metrics (latency, tokens, cost, retries, errors) → eval reports + dashboard page
                 Config (pydantic-settings: .env secrets; policy.yaml; models.yaml)
                 Logging (stdlib `logging`, one JSON line per event with trace_id; a redaction filter runs before any handler)
```

### The agent loop, in pseudocode

```python
def on_event(defense_id, event):
    with repo.lock(defense_id):                    # one writer per defense
        state = repo.load(defense_id)
        handlers.apply(state, event)                # deterministic: timers, statuses, extraction results
        if not needs_agent(state, event):           # e.g. reminder timer fired → handled by code
            return repo.save(state)
        run = tracer.start_run(defense_id, event)
        for step in range(cfg.max_steps_per_wake):  # placeholder: 8
            snapshot = build_snapshot(state)        # compact, pseudonymized, includes allowed tools
            decision = llm.plan(snapshot, tools=allowed_tools(state.status))
            if budget.exceeded(): return escalate(state, "BUDGET")
            call = validate_tool_call(decision, state)   # schema, state guard, authz, policy, rate limit
            if call.invalid:
                state.record_agent_error(call.error); continue   # the agent sees the error on the next step
            result = tools.execute(call, state)     # read-only, auto-send, or create ApprovalRequest
            state.record(call, result)
            if call.tool == "wait": break
        else:
            escalate(state, "STEP_BUDGET")          # the agent never ended its turn
        repo.save(state)                            # optimistic version check
```

---

## Responsibility matrix

One row per decision. **A** = agentic (LLM decides), **D** = deterministic code, **H** = human (student). Other people act outside the system.

| # | Decision | Owner | Why this owner | Safety net |
|---|---|---|---|---|
| 1 | Is this inbound message from a committee member of this defense? | D | Address and thread-token matching has a right answer. | Unknown sender → quarantine (H reviews) |
| 2 | What does this reply say (status, intervals, conditions)? | A (extractor) | Free text needs language understanding. | Schema validation, confidence threshold, H review queue |
| 3 | Which exact dates and times does "Tuesday afternoon" mean? | D | Time math. The LLM must not do it (brief). | Resolver unit and property tests |
| 4 | Is this statement ambiguous, contradictory, or out of window? | D + A | The extractor flags language issues. Code checks ranges and conflicts with earlier statements. | Flags shown on the board |
| 5 | Which slots are feasible (roles, notice, term, duration, hours, rooms)? | D | Policy and set intersection. | Oracle comparison in evaluation |
| 6 | Send a routine reminder now? | D | A fixed cadence from policy is enough. | Rate limit per member |
| 7 | **Ask a clarification, wait, or move ahead with partial information?** | **A** | Depends on which missing answer blocks the most slots, how close the notice deadline is, and conditions. Rules for this become large and brittle. | Tool allow-list, per-member message limit |
| 8 | **What exactly to ask** (which slot or condition to confirm) | **A** (text) + D (template, validator) | Targeted questions reduce back-and-forth. | Output validator (no private data, only in-window dates, length cap) |
| 9 | **What to do with a non-responder after the last reminder** (wait, treat as non-blocking if optional, propose substitute, escalate) | **A** proposes; H approves anything that changes the committee | Depends on the role, time left, and the other replies. | Substitute always needs H; mandatory roles cannot be skipped (D) |
| 10 | **Which feasible slot to propose** | **A** chooses from the solver's top list; D ranks | Soft factors: a hybrid condition, a member's "prefer mornings", risk from members with low confidence. | Validator: the choice must be in the current feasible set |
| 11 | Which room | D | Smallest free room that fits capacity and hybrid needs. | Room re-check at booking |
| 12 | Book room and send invites | H approves → D executes | Consequential and visible to others. | Hash-checked approval, idempotency |
| 13 | Announcement text | D (template) | Formal content; no need for an LLM. | H approval |
| 14 | Send announcement | H approves → D executes | Public and hard to undo. | Notice check just before sending |
| 15 | **Re-planning strategy after a disruption** (ask one member, try near-miss slots, re-poll everyone, propose substitute) | **A** proposes; H approves re-poll, cancellation, or substitute | Main agentic value: pick the cheapest recovery. | Near-miss data comes from D |
| 16 | Escalate to the student | A or D | A: "I'm stuck". D triggers: budget, deadline, repeated tool errors, step budget. | Always allowed |
| 17 | Change committee, roles, or policy | H only | Authority lies outside the student and the system. | No tool exists for it |
| 18 | Release a quarantined message | H only | Possible attack or spoofing. | Audit log |
| 19 | Who may see or do what | D | Access control. | Security tests |

**Where the agent really is:** rows 7, 8, 9, 10, and 15. Everything else is deliberately deterministic or human.
If the evaluation shows the fixed-rule baseline (B1) matches the agent on these decisions, that is an honest finding and must be reported (see `risks.md`).

---

## Technology choices

| Technology | Why needed | Simpler alternative | Core or optional |
|---|---|---|---|
| **Python 3.12** | Given. Good LLM SDKs and testing tools. | — | Core |
| **Pydantic v2** | Schemas for tool inputs and outputs, extraction output, API bodies, config. The main validation tool. | dataclasses with hand-written checks (more code, more bugs) | Core |
| **pydantic-settings + YAML** | Central config: `.env` for secrets, `policy.yaml`, `models.yaml` (model names, prices, timeouts). | Constants in code (breaks "centralized configuration") | Core |
| **FastAPI + Uvicorn** | JSON API with typed contracts, dependency-based auth, and HTML pages. | Streamlit: faster to start, but its rerun model is awkward for event-driven state and approvals, and there is no real API layer | Core |
| **Jinja2 templates** | Server-rendered dashboard pages, no JavaScript build. | A React SPA (too much work for a solo project) | Core |
| **HTMX** (single JS file) | Refresh parts of the board without a full page reload. | Plain forms and full reloads (fine as a fallback) | Optional |
| **SQLite (stdlib `sqlite3`)** | Transactions, restart after a crash, event log, easy to inspect. One file, nothing to install. | JSON files (no transactions, race conditions) | Core |
| **SQLAlchemy / SQLModel** | Only if raw SQL becomes painful. | stdlib `sqlite3` plus a small repository class (recommended to start) | Optional |
| **One LLM provider SDK** (provider to be decided) | Structured output or tool calling for the extractor and planner. | Raw HTTP (more error handling to write) | Core |
| **tzdata** | IANA time zones for `zoneinfo` on Windows. | None; required on Windows | Core |
| **pytest** | Unit, integration, failure, and security tests; evaluation harness helpers. | unittest (more boilerplate) | Core |
| **Hypothesis** | Property tests for the resolver and solver (for example, "a solver result never contains a busy interval"). | Hand-written examples only | Optional (strong value) |
| **Ruff** | Lint and format in one tool. | flake8 + black | Core |
| **In-memory mock mailbox** | Deterministic email for tests and demo. | — | Core |
| **Mailpit** (local SMTP UI; Windows binary exists) | Show "real" emails in the demo. | The in-app message viewer | Optional |
| **Own tracer** (SQLite table + JSONL) | Spans for LLM and tool calls: latency, tokens, cost, errors. | print logs (not enough for AgentOps) | Core |
| **OpenTelemetry / Langfuse** | Standard tracing UI (bonus: advanced AgentOps). Langfuse cloud needs no Docker. | Own tracer only | Optional |
| **GitHub Actions** | Run lint, tests, and the offline evaluation (FakeLLM) on every push (bonus: CI and evaluation gates). | Run locally | Optional (cheap, recommended) |
| **gitleaks / Dependabot** | Secret and dependency scanning (bonus: DevSecOps). | Manual review | Optional |
| **Docker** | Reproducible run for graders. | venv setup (default, ADR-012) | Optional |

**Supporting libraries.** These are small and widely used, and each is needed by a component above. They are listed here so that no dependency enters the project undocumented. **Rule: a new runtime dependency is added to this table first, with its reason.**

| Library | Needed for | Stage |
|---|---|---|
| `PyYAML` | Reading `policy.yaml`, `models.yaml`, and scenario files | ST-02 |
| `email-validator` (via `pydantic[email]`) | `EmailStr` fields in `interfaces.md` | ST-02 |
| `argon2-cffi` | Password hashing for UI and API users | ST-12 |
| `itsdangerous` | Signed session cookies (Starlette `SessionMiddleware`) | ST-12 |
| `python-multipart` | HTML form posts in FastAPI | ST-12 |
| `httpx` (dev) | FastAPI `TestClient` in API tests | ST-12 |
| `pytest-cov` (dev) | Coverage reports and the coverage targets in the roadmap | ST-00 |

### Setup without Docker (Windows, default)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # includes tzdata, pytest, ruff
copy .env.example .env           # then put the API key in .env (never commit it)
python -m app.cli init-db
python -m app.cli seed-demo      # loads demo scenario and personas
uvicorn app.main:app --reload    # dashboard at http://127.0.0.1:8000
python -m eval.run --suite dev --llm fake    # offline, free
```

With Docker (optional): `docker compose up`. It runs the same commands inside a container, with `.env` mounted and not copied into the image.

### Proposed repository layout

```text
app/
  api/            # FastAPI routers, auth dependencies, error handlers
  ui/             # Jinja2 templates, static files
  core/           # domain models (Pydantic), state machine, config
  agent/          # planner prompt, snapshot builder, loop, tool registry
  tools/          # T01–T11 implementations (thin; call services)
  services/       # policy engine, resolver, slot solver, room filter, output validator, executor
  inbound/        # pipeline: dedupe, sender check, extractor, checks
  adapters/       # interfaces + mocks (email, calendar, rooms, clock), LLMClient + FakeLLM
  storage/        # SQLite repository, migrations
  observability/  # tracer, metrics, redaction
config/           # policy.yaml, models.yaml, reminder policy
eval/             # scenarios, personas, fixtures (cached replies), oracle, baselines, runner, reports
tests/            # unit/, integration/, failure/ (FM-xx), security/ (SEC-xx)
docs/             # these documents
research/         # interview sheets, sources
```
