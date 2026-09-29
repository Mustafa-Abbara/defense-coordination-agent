# Risks

A critical review of this design. Each risk has a mitigation, and most have an early warning sign to watch for.
Related documents: all others. `evaluation.md` is where most mitigations are tested.

## Strongest part

**The safety architecture, and an evaluation that can check it.**
- The LLM never owns hard constraints (ADR-004).
- Email text is read by a tool-less extractor, and the planner never sees it (ADR-005).
- Consequential actions go through hashed approvals run by deterministic code (ADR-009).
- The oracle knows the ground truth, so "0 violations" is measured, not assumed.

This is easy to explain on a poster and easy to show live (inject an attack, show that nothing happens).

**Keep it strong:** make SEC-01 to SEC-12 and the zero-violation metric part of CI early (Week 3–4), not at the end.

## Weakest part

**The value of the agent is not yet proven, and all real-world facts are assumptions.**
- There are no policy sources and no interviews yet (`problem.md` has 0 DOCUMENTED claims).
- It is possible that a well-designed rule system (B1 plus a "clarify if unclear" rule) performs almost as well as the agent.

**Mitigations:**
1. Do 3 interviews and collect sources S1–S3 **before the poster pitch**. Even 3 conversations change the grade on problem understanding.
2. Add an optional stronger baseline, **B1c = B1 + rule-based clarification** ("if a statement has an issue, send one templated question"). If the agent does not beat B1c, report that honestly and move the claim to the areas where it does help: re-planning after disruptions (S17–S24) and non-responder strategy (S11, S20).
3. Present the result as "where agency helps and where it doesn't". The course rubric rewards this ("clear understanding of its limitations").

---

## Where the system could be "fake agentic"

| # | Weak spot | Why it is a problem | Fix / check |
|---|---|---|---|
| F1 | The planner always follows the same sequence: snapshot → find slots → propose top slot | Then it is a fixed workflow with an expensive `if` statement | Measure **action diversity** in traces: distribution of tool sequences per category. Count how often the agent picks a slot other than rank 1, and whether that helped. If the sequence is always the same, simplify to code and say so |
| F2 | "Clarify whenever there is an issue" is a one-line rule | The agent adds nothing over B1c | B1c baseline (above). Give the agent's clarification decisions real trade-offs: which member blocks the most slots, the time left before the notice deadline, the per-member message budget |
| F3 | The extractor is called "agentic" | It is an LLM function (no tools, no loop) | Call it what it is on the poster: "LLM extraction component". The agent is the planner loop |
| F4 | Personas react to metadata, not to the agent's text | The "conversation" is partly simulated. Poor wording is not penalized | Manual message review (`evaluation.md`). Optional live-LLM persona stress test, reported separately |
| F5 | Re-planning always ends in "re-poll everyone" | That is what B1 does | Track the **recovery strategy used** per disruption scenario and emails per member (M-06). The claim is "fewer emails, same or better success" |
| F6 | The agent escalates too often "to be safe" | High success on paper, but no real automation | M-05 (unnecessary escalation rate) and M-07 (human burden) are reported next to M-01 |

## What could be over-engineered (cut order if time is short)

Cut from the top. Everything from "Core" in `architecture.md` stays.

1. Live-LLM persona mode (optional stress test)
2. Small vs. large planner model comparison
3. Langfuse / OpenTelemetry (the own tracer is enough for the rubric; add only for bonus credit)
4. Mailpit and Docker (useful for graders, not needed for the grade)
5. Calendar free/busy integration (FR-11 is a COULD)
6. HTMX partial refresh (full page reloads are fine)
7. The substitute flow (FR-20; keep it as an escalation with a drafted message)
8. Hash-chained event log: cheap (about 20 lines) and useful for the tampering story. Keep it unless really stuck

**Signs of over-engineering:** a component with no test and no metric that uses it; a config option that no scenario changes; any second "agent".

---

## Technical risks

| ID | Risk | Likelihood / impact | Mitigation | Early warning |
|---|---|---|---|---|
| RK-T1 | Date and time resolution bugs (DST, "next Tuesday" at the week boundary, day/month order) | High / High | Resolver is pure code with unit and property tests (Hypothesis). All times in UTC. `tzdata` installed. S29–S32 | A failing property test; an oracle mismatch in time zone scenarios |
| RK-T2 | State machine grows too complex to finish solo | Medium / High | 11 defense states only; a transition table in one module; an illegal transition raises an error. Build `COLLECTING → AWAITING_APPROVAL → BOOKING → CONFIRMING → SCHEDULED` first, then `RESCHEDULING` | More than 2 days spent on transition bugs |
| RK-T3 | Planner outputs are inconsistent across runs | Medium / Medium | Temperature 0. State-filtered tools. The validator catches invalid calls. 3 seeds. Report the variance | High variance across seeds on dev |
| RK-T4 | Structured-output or tool-calling differences between providers | Low / Medium | One provider (ADR-008). Pydantic validation on every output regardless of provider features | — |
| RK-T5 | Context snapshot grows too big (cost, confusion) | Medium / Medium | Hard size budget (under 3k tokens), top-5 lists, last 10 events; a test on a 7-member worst case | Tokens per wake-up rising in traces |
| RK-T6 | Solo developer, basic Python, first agent project | High / High | Build deterministic parts first (they are ordinary Python). Use `FakeLLM` so the loop can be tested without an API. AI coding help plus a rule: **no merge without a test you understand**. Weekly scope check against the roadmap | Falling behind the roadmap by more than one week |
| RK-T7 | Budget unknown; evaluation cost may be too high | Medium / Medium | Budget cap in code (FM-24). Measure tokens on pilot runs. Cost levers in `evaluation.md` (small extractor model, fewer seeds on the ablation) | Pilot tokens per run above about 150k |
| RK-T8 | Windows-specific problems (paths, time zones, `uvicorn --reload`, file locks on SQLite) | Medium / Low | `pathlib` everywhere; `tzdata`; CI on `windows-latest` plus `ubuntu-latest` (optional) | — |

## Evaluation risks

| ID | Risk | Mitigation |
|---|---|---|
| RK-E1 | **Author bias.** You write scenarios your system handles | Held-out written and sealed early. Ideally a classmate writes 3–5 held-out replies. Hand-written cases from interviews |
| RK-E2 | Small sample (40 scenarios, 10 held-out) | Report Wilson intervals and paired wins/losses. Claim only large differences and zero-violation results (with the rule-of-three caveat) |
| RK-E3 | Synthetic replies are cleaner than real ones | Paraphrases plus hand-written cases. Accuracy reported by text source. The gap is shown openly |
| RK-E4 | **Oracle bugs** make wrong outcomes look right | The oracle is separate from the solver code (written independently, simpler brute force over 15-minute steps). Unit tests. Spot-check 5 runs by hand |
| RK-E5 | Unfair baselines (too weak) | Same extractor, mocks, clock, and validators. B1c added. Baselines frozen before the final run |
| RK-E6 | Scripted student behaves differently from a real one | Documented rule (approve when all checks pass). One small real-user trial in the UI if possible (2 students, think-aloud, 15 minutes) |

## User-validation risks

| ID | Risk | Mitigation |
|---|---|---|
| RK-U1 | No interviews happen (time, access) | Ask this week. Three short conversations are enough. If none happen, say so on the poster and use the assumption register |
| RK-U2 | Interviews show that poll tools (Doodle, When2meet) already solve the problem | Narrow the value claim to what polls don't do: chasing, vague and conditional replies, policy checks, re-planning after disruptions, privacy |
| RK-U3 | The coordinator, not the student, does the scheduling | Change the primary user. The architecture barely changes (the approver role moves) |
| RK-U4 | Faculty dislike messages sent by an assistant | Messages go from the student's address with a clear footer (A-16); few messages (M-06); all wording shown before approval for multi-recipient messages |
| RK-U5 | Sending faculty emails to an external LLM provider is not acceptable at the university | Synthetic data only in this project; state it as a deployment blocker to resolve (source S6); an optional local-model path is future work |

---

## Reasons a professor might reject it, and the answer

| Objection | Answer prepared in advance |
|---|---|
| "This is just a scheduler with an LLM parser." | Responsibility matrix (`architecture.md`): agentic decisions are rows 7–10 and 15. Evidence: agent vs. B1 and B1c on disruption and non-responder scenarios, plus action-diversity analysis. If the difference is small, we say so and show where it is large |
| "Doodle already exists." | Polls collect answers from people who answer the poll. They don't chase, interpret conditions, check policy, book, or re-plan. Interview evidence (RK-U2) |
| "Where are the users?" | Grounding plan with 3–5 conversations; recording sheets; assumption register showing what changed |
| "Your evaluation uses your own synthetic data." | Sealed held-out set, paraphrases, hand-written cases, results by text source, fair baselines, all runs reported |
| "Policy values are made up." | They are explicitly placeholders with assumption IDs, not claims. The source checklist shows the plan. The design is configuration-driven, so real values change a YAML file only |
| "Too big for one person." | MVP cut line in the roadmap; cut order above; deterministic core first |
| "Security is just prompt instructions." | No: security comes from missing tools, validators, sender verification, output validation, and hashed approvals. The prompt is the last layer. SEC tests show attacks fail even when the model is fooled (M-11b) |
| "Isn't this touching healthcare? Members may mention medical reasons." | No. The system schedules meetings. It never asks for reasons, never analyzes them, and stores volunteered reasons only in a restricted field shown to the owner student (`data_model.md`). No health information is processed for any purpose |
| "The demo is a happy path." | The demo script includes a room loss, an injection, a spoofed sender, and an LLM outage. Preset inject events are ready for live requests |
