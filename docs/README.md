# Thesis Defense Coordination Agent: Design Documents

Agentic Systems 503N/798S, Fall 2026, Path A (application-oriented). Solo project.

One orchestrating agent, deterministic services, and human approval coordinate a thesis defense from the first availability request to the confirmed booking and announcement. It keeps working for weeks while replies arrive late, vague, or not at all, and it re-plans when things change.

## Documents

| # | File | What it contains |
|---|---|---|
| 1 | [problem.md](problem.md) | Users, current workflow, pain points, **assumption register (A-01…A-20)**, source checklist, interview plan and templates |
| 2 | [requirements.md](requirements.md) | Functional (FR-01…FR-27) and non-functional (NFR-01…NFR-12) requirements, success criteria (SC-01…SC-08), real-world constraints (C-01…C-06) |
| 3 | [architecture.md](architecture.md) | Decision records (ADR-001…ADR-015), component diagram, agent loop, **responsibility matrix**, technology choices and supporting libraries, Windows setup without Docker |
| 4 | [data_model.md](data_model.md) | Entities, placeholder policy config, visibility rules, PII, retention, redaction, **memory = structured state** |
| 5 | [state_machine.md](state_machine.md) | Defense states and member states, allowed tools per state, simulated clock |
| 6 | [interfaces.md](interfaces.md) | Service interfaces, **agent tools T01…T11**, inbound email safety pipeline, extraction schema, HTTP API |
| 7 | [approval_policy.md](approval_policy.md) | Risk tiers R0–R3, action rules AP-01…AP-14, what is never allowed, how approval burden is measured |
| 8 | [failure_matrix.md](failure_matrix.md) | 26 failure scenarios (FM-01…FM-26) with detection, recovery, class, and test IDs |
| 9 | [threat_model.md](threat_model.md) | Assets, trust boundaries, threats TH-01…TH-13, security tests SEC-01…SEC-12 |
| 10 | [evaluation.md](evaluation.md) | 40 scenarios (S01…S40), 12 personas, simulation design, oracle, baselines (B1, B1c, B2), ablation, metrics M-01…M-13 |
| 11 | [risks.md](risks.md) | Strongest and weakest parts, "fake agentic" checks, cut order, risks, and answers to likely objections |
| 12 | [roadmap.md](roadmap.md) | **Build plan:** stages ST-00…ST-21, scope tiers, calendar, bonus picks, demo script and backups, report outline, Definition of Done |
| 13 | [ui.md](ui.md) | Screens mapped to the student's tasks, emails as the committee's interface, error states, usability check |
| 14 | `progress.md` (created in ST-00) | One entry per finished stage: what was built, test results, open issues. The next session starts from here |

**Suggested reading order:** problem → requirements → architecture → state_machine → interfaces → the rest. Start building from roadmap.md.

## Decisions recorded from your answers (29 Sep 2026)

| Topic | Decision | Where |
|---|---|---|
| Final demo | First half of December 2026; slot 7–10 min → 8:30 script | `roadmap.md` → Demo script |
| Poster pitch date | **Unknown.** The roadmap assumes late October (ASSUMPTION) | Roadmap below |
| LLM provider and budget | **Not decided.** Provider-neutral `LLMClient`, budget cap in config, a cost formula to fill in | ADR-008, `evaluation.md` → Cost estimate |
| Machine | Windows; **no Docker by default** (Docker optional) | ADR-012 |
| Policies and workflow sources | **None yet.** Everything is ASSUMPTION or TO BE VALIDATED BY INTERVIEW; placeholders in `policy.yaml` | `problem.md` |
| Interface | Dashboard, not chat: FastAPI + server-rendered pages (board, availability grid, approval inbox, review queue, traces) | ADR-007 |
| Simulated replies (question 7) | Structured ground truth + templates + **LLM paraphrases generated once and cached** + hand-written edge cases. No LLM in the simulator during runs; live-LLM personas only as an optional stress test | ADR-011, `evaluation.md` |
| Hours per week | Not a constraint; the roadmap is phased by milestones | Roadmap below |

## Poster section → where the content is

| Poster section (required) | Source in these documents |
|---|---|
| Problem / Research Question | `problem.md` → Pain points; `requirements.md` → C-01 |
| Users & Current Workflow | `problem.md` → Users, Current workflow (with labels), grounding plan |
| Agentic Justification | `architecture.md` → Summary, responsibility matrix ("where the agent really is"); `risks.md` → fake-agentic checks |
| Architecture | `architecture.md` → component diagram; `state_machine.md` → diagram; `interfaces.md` → pipeline diagram |
| Success Criteria & Evaluation Plan | `requirements.md` → SC-01…SC-08; `evaluation.md` → baselines, metrics, splits |
| Real-World Constraints | `requirements.md` → C-01…C-04 (evaluated), C-05, C-06 |
| AgentOps, Reliability & Security Plan | `data_model.md` → TraceSpan, redaction; `failure_matrix.md`; `threat_model.md`; `approval_policy.md` |
| Pilot Evidence / Preliminary Results | "Pilot evidence for the poster" (below); `roadmap.md` → ST-10 |
| Roadmap | `roadmap.md` (calendar and stages) |

## Roadmap

The full build plan is in **[roadmap.md](roadmap.md)**. It has:
- 22 stages (ST-00…ST-21) in dependency order, each with acceptance criteria, hours, grading category, and scope tier;
- a week-by-week calendar and the critical path;
- the bonus practices;
- the demo script and backup recordings;
- the report outline;
- the Definition of Done.

Key dates (partly ASSUMPTION): held-out set sealed by the end of October · poster pitch late October (date to confirm) · **MVP cut line 15 November** · evaluation freeze in the week of 30 November · live demo in the first half of December.

### Pilot evidence for the poster (achievable by late October)

1. **Extraction accuracy** on about 40–60 labeled replies, split by source (template, paraphrase, hand-written). This is real, measured evidence.
2. **Deterministic core tests:** the number of resolver and solver tests, including property tests (for example, "no proposed slot overlaps a busy interval").
3. **2–3 dev scenarios end-to-end** with traces, agent vs. B1 (clearly labeled as preliminary, dev set, small n).
4. **Interview summary:** how many conversations, which assumptions were confirmed, changed, or rejected (from the recording sheets).
5. **Failure Matrix and threat model** as tables, with the tests that already pass.

Do not show held-out numbers on the poster. They do not exist yet, and they must stay sealed.

## Open items for you

- [ ] Poster pitch date → update the calendar in `roadmap.md`.
- [ ] LLM provider and total budget → fill in ADR-008 and prices in `config/models.yaml`, and set the budget caps.
- [ ] Is Docker available (for the optional bonus)?
- [ ] Collect sources S1–S6 and schedule 3–5 interviews (`problem.md`).

## ID glossary

ST = roadmap stage · G1–G7 = grading category · A = assumption · S1–S6 = sources to collect · PP = pain point · FR / NFR = requirements · SC = success criteria · C = constraint · ADR = decision record · T = agent tool · AP = approval rule · R0–R3 = risk tiers · FM = failure-matrix row · TH = threat · SEC = security test · S01–S40 = evaluation scenario · P = persona · M = metric · EQ = evaluation question · RK = risk
