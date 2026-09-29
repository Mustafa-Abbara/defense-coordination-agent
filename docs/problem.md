# Problem

Project: **Thesis Defense Coordination Agent** (Agentic Systems 503N/798S, Fall 2026, Path A).

## How to read this document

Every claim has one of three labels:

| Label | Meaning |
|---|---|
| **DOCUMENTED** (source) | Backed by a public source listed in the Sources section. |
| **TO BE VALIDATED BY INTERVIEW** | Plausible and central to the project. It must be checked with real users (see the grounding plan). |
| **ASSUMPTION** | A working guess used so design can continue. It has an ID (A-xx) so other documents can refer to it. |

**Current status: there are no DOCUMENTED claims yet.** No public policy or workflow source has been collected so far.
Every policy value in the system (notice days, duration, required roles, and so on) is a configurable placeholder (see `data_model.md` → PolicyConfig).
The "Source collection checklist" below lists what to find first.

---

## Users

### Primary user: the graduate student (defending candidate)

- Coordinates their own defense: finds a date that works for the committee, books a room, sends invites and the announcement. — TO BE VALIDATED BY INTERVIEW (A-01)
- Often has low authority over the committee. They cannot "require" a professor to answer quickly. — TO BE VALIDATED BY INTERVIEW (A-14)
- Is the **operator** of the system. They set up the defense, watch the dashboard, and approve consequential actions.

### Secondary users

| User | Role in the workflow | How they touch the system |
|---|---|---|
| **Advisor** | Committee member, usually mandatory. May need to agree on the final date and on any substitute member. — TO BE VALIDATED BY INTERVIEW (A-11) | Only by email, like other members. An optional read-only dashboard view (role `observer`). |
| **Committee members** (4–7 people, some roles mandatory) | Reply with availability in free text, late or not at all. May be external or in another time zone. — TO BE VALIDATED BY INTERVIEW (A-02, A-18) | **Email only.** They never log in. The system must not add work for them. |
| **Graduate coordinator** (department or graduate office) | Knows the policies. May handle room booking, announcements, and approval of substitutes. — ASSUMPTION (A-08, A-09, A-11) | Receives drafted requests, sent only after the student approves them. An optional read-only view. |

---

## Current workflow

No public source has been provided, so the whole workflow below is **ASSUMPTION** or **TO BE VALIDATED BY INTERVIEW**.
The steps come from the project brief. Interviews must confirm or correct them.

| # | Step (as assumed today) | Label |
|---|---|---|
| W1 | Student and advisor agree the thesis is ready and choose a rough window (for example, "late November"). | TO BE VALIDATED BY INTERVIEW (A-13) |
| W2 | Student checks rules: notice period, semester dates, defense duration, required committee roles. | ASSUMPTION (A-04, A-05, A-06, A-07) |
| W3 | Student emails all committee members asking for availability (free text or a poll link). | TO BE VALIDATED BY INTERVIEW (A-03) |
| W4 | Replies arrive over days. Some are vague ("Tuesday afternoon works"), conditional ("only if hybrid"), or deferred ("ask me next week"). Some members never reply. | TO BE VALIDATED BY INTERVIEW (A-15) |
| W5 | Student sends reminders and follow-up questions by hand. | TO BE VALIDATED BY INTERVIEW (A-14) |
| W6 | Student finds a date that works for all mandatory members, often by hand in a spreadsheet or on paper. | TO BE VALIDATED BY INTERVIEW |
| W7 | Student books a room (possibly through a coordinator or a booking system). The booking may be rejected or lost later. | ASSUMPTION (A-08) |
| W8 | Student sends calendar invites and a public announcement, respecting the notice period. | ASSUMPTION (A-05, A-09) |
| W9 | Something changes (a member cancels, a room is lost, the chair asks for hybrid). The student goes back to W3–W8. | TO BE VALIDATED BY INTERVIEW |
| W10 | If a member cannot attend at all, the student asks the advisor or coordinator about a substitute. | ASSUMPTION (A-11) |

---

## Pain points

All pain points are **TO BE VALIDATED BY INTERVIEW** until interview notes exist.

| ID | Pain point | Why it hurts |
|---|---|---|
| PP-1 | **Free-text replies are hard to combine.** "Thursday except 2–4" and "afternoons in week 2" must be turned into one shared picture. | Manual intersection is slow and error-prone. |
| PP-2 | **Chasing people.** Tracking who replied, who needs a reminder, and who was asked a follow-up question. | Mental load. Reminders sent too early or too late annoy faculty. |
| PP-3 | **The situation changes while you wait.** Early replies go stale. The notice deadline moves closer every day. | Slots that were possible become impossible without anyone noticing. |
| PP-4 | **Policy checks are easy to forget.** Notice period, semester end, duration, required roles. | A booked defense may have to be cancelled. This is costly and embarrassing. |
| PP-5 | **Disruptions restart the process.** A cancellation or lost room means re-polling everyone. | Often only one member needs to be asked again, but the student re-polls all. |
| PP-6 | **Privacy friction.** Members give reasons ("I'm teaching", "medical appointment", "travelling"). These should not be forwarded to others. | Reply-all threads can leak these reasons. |

### Tasks the system improves

| Task | How | Pain point |
|---|---|---|
| Turn free-text replies into structured availability | LLM extraction, then deterministic date and time resolution, then validation | PP-1 |
| Decide who to ask what, and when | Agent loop with state, timers, and targeted clarification | PP-2, PP-3 |
| Enforce policy on every proposed slot | Deterministic policy engine and slot solver | PP-4 |
| Re-plan after a disruption with the fewest new emails | Agent uses near-miss slots and asks only the affected member | PP-5 |
| Keep reasons private | Private reasons are stored separately. Outbound messages are validated. Members are pseudonymized for the planner. | PP-6 |
| Book, invite, announce | Deterministic executor, run only after student approval | PP-4 |

**Not in scope:** thesis content, grading, the defense itself, degree audit, or anything done after the defense.

---

## Assumption register

Each assumption can be confirmed, changed, or rejected by interviews or sources.
Code reads policy values from `config/policy.yaml`. That file points back to these IDs.

| ID | Assumption | Where it is used | How to check |
|---|---|---|---|
| A-01 | The student coordinates the defense (not the coordinator). | Primary user, UI | Interview Q1 |
| A-02 | A committee has 4–7 members. Some roles are mandatory. | Data model, scenarios | Source checklist S2; interview Q2 |
| A-03 | Coordination happens mainly by email in free text. | Inbound pipeline | Interview Q3 |
| A-04 | Required roles (for example, advisor, chair, external examiner) are defined by policy. | PolicyConfig `required_roles` | Source S2 |
| A-05 | A minimum notice period exists between announcement and defense. | PolicyConfig `notice_days` | Source S3 |
| A-06 | Defenses must happen within semester or term dates. | PolicyConfig `term_windows` | Source S1 |
| A-07 | Defense duration is fixed per degree level. | PolicyConfig `duration_minutes` | Source S2 |
| A-08 | Room booking goes through a request that can be accepted, rejected, or later cancelled. | RoomService mock | Source S4; interview Q7 |
| A-09 | A public announcement must be sent before the defense. | Announcement step | Source S3 |
| A-10 | Some members may attend remotely (hybrid) under some conditions. | PolicyConfig `remote_allowed_roles` | Source S2; interview Q6 |
| A-11 | Replacing a committee member needs approval by someone other than the student. | Substitute tool, human only | Source S2; interview Q9 |
| A-12 | Faculty do not share full calendars. Free/busy sharing is opt-in at most. | CalendarService, privacy | Interview Q5 |
| A-13 | Coordination takes days to weeks. | Simulated clock, metrics | Interview Q4 |
| A-14 | The student spends real effort chasing replies. | Value claim | Interview Q4, Q8 |
| A-15 | Many replies are late, vague, conditional, or missing. | Personas, scenarios | Interview Q3; anonymized examples |
| A-16 | Faculty accept messages sent on the student's behalf (from the student's address, with a clear footer). | Email design | Optional faculty conversation; Q10 |
| A-17 | The student accepts roughly 3–6 approval clicks per defense. | Approval policy target | Interview Q10 |
| A-18 | Some members are abroad, in other time zones. | Time zone handling | Interview Q2 |
| A-19 | Defenses happen within working hours (placeholder 08:00–18:00 local). | PolicyConfig `working_hours` | Source S2 |
| A-20 | "Morning" and "afternoon" mean fixed ranges (placeholder 08:00–12:00 and 13:00–17:00). | Date/time resolver | Interview Q3 |

---

## Source collection checklist

Collect these **before the poster pitch** if possible. For each one, save the URL or PDF, the date you accessed it, and the exact sentence you rely on.
Then change the matching assumption label to **DOCUMENTED (source)**.

| ID | What to find | Replaces |
|---|---|---|
| S1 | Academic calendar: term dates, exam periods, holidays | A-06 |
| S2 | Graduate catalogue or thesis regulations: committee composition, required roles, external members, remote participation, substitutes, defense duration | A-02, A-04, A-07, A-10, A-11, A-19 |
| S3 | Defense announcement rules: notice period, who sends it, where it is posted | A-05, A-09 |
| S4 | Room booking procedure: who books, how far ahead, typical rejection reasons | A-08 |
| S5 | Any department form or checklist for scheduling a defense | W1–W10 |
| S6 | University rules on email or data privacy, and on using third-party AI services | Constraint C-03 in `requirements.md` |

If a document cannot be found, keep the ASSUMPTION label. Say so on the poster ("policy values are configurable placeholders pending confirmation").
This is honest and acceptable. Inventing values is not.

---

## Grounding plan

### Who and how many

- **3–5 short conversations** (15–20 minutes each):
  - 2–3 graduate students who defended recently (last 12 months) or are scheduling now
  - 1 graduate coordinator or department administrator
  - Optional: 1 faculty member who often sits on committees
- Ask about **past behavior** ("last time you…"), not opinions about a future tool.
- Get verbal consent. Record notes only, not audio (unless the person agrees). No names in the notes.
- **Before the first conversation, ask the instructor** whether informal needs-finding conversations for a course project need any ethics approval at the university. Keep them informal: no recordings by default, no personal data, no identifiable quotes.

### Interview questions (about past behavior)

Students:

1. Q1 — Think about your last defense (or one you helped with). Who did the scheduling work? Walk me through the first message you sent.
2. Q2 — How many committee members were there? What roles? Were any external or abroad?
3. Q3 — How did people reply? Could you show me (anonymized) two or three real replies? Which ones were hard to interpret?
4. Q4 — How many days passed from the first message to a confirmed date? Where did most of the waiting happen?
5. Q5 — Did anyone share a calendar or use a poll tool (Doodle, When2meet, etc.)? What happened with the members who did not use it?
6. Q6 — Did any member have conditions (remote only, only mornings, only if another person attends)? How did you handle them?
7. Q7 — How did you book the room? Was a request ever rejected or cancelled? What did you do?
8. Q8 — How many reminders or follow-ups did you send? How did you decide when to send them?
9. Q9 — Did a member ever drop out or cancel late? What happened next, and who had to approve changes?
10. Q10 — If a tool drafted messages and booked things for you, which steps would you want to check yourself before they happen?

Coordinator:

11. Q11 — What are the rules you check most often (notice, roles, duration, term dates)? Where are they written down? What mistakes do students make most often?
12. Q12 — What information do you need from a student to book a room and publish an announcement? How long does it take?

### What to record (anonymized)

Use one recording sheet per conversation (template below). Store it in `research/interviews/` in the repository.
**No names, emails, or identifiable course numbers.** Replace real reply examples with paraphrases that keep the difficulty (vagueness, condition, contradiction) but remove identity.

```markdown
## Interview IV-0X
- Date: YYYY-MM-DD
- Participant type: student (MSc / PhD) | coordinator | faculty
- Consent for notes: yes/no; consent to quote paraphrased replies: yes/no
- Committee size and roles (counts only):
- Days from first message to confirmed date:
- Number of reminders sent:
- Example replies (paraphrased, anonymized):
  1.
  2.
- Disruptions experienced (cancellation, room loss, requirement change):
- Rules mentioned (with where they are written, if known):
- Steps they would want to approve themselves:
- Surprises / things that contradict our assumptions:
- Assumptions affected: A-__ confirmed | A-__ changed to "..." | A-__ rejected
```

### How findings become requirements

1. After each conversation, fill in the "Assumptions affected" line.
2. For each **changed** assumption, update the matching requirement in `requirements.md` or the value in `config/policy.yaml`. Add a line to the change log at the end of this file.
3. For each new difficulty seen in real replies (for example, a new kind of vague phrase), add a paraphrased example to the evaluation reply bank (`eval/fixtures/replies/`) as a **hand-written edge case**, and add or update a scenario in `evaluation.md`.
4. If a finding shows a pain point is not real (for example, everyone uses a poll tool and it works), say so on the poster and narrow the scope. Do not hide it.

### Which assumptions each finding could confirm or change

| Finding type | Assumptions affected | Design impact if changed |
|---|---|---|
| Who does the scheduling | A-01 | Primary user and UI change (for example, a coordinator dashboard for many defenses) |
| Committee size and roles | A-02, A-04, A-18 | Scenario generator ranges; PolicyConfig roles |
| Reply styles | A-03, A-15, A-20 | Extractor prompt and schema, persona templates, resolver defaults |
| Time to confirm | A-13, A-14 | Baseline expectations, clock ranges, value claim on the poster |
| Poll tool usage | A-03, A-12 | If poll tools solve PP-1, focus the value claim on PP-2 to PP-5 |
| Room process | A-08 | RoomService mock behavior (delays, rejection rate) |
| What they want to approve | A-17 | Approval tiers in `approval_policy.md` |
| Substitutes and approvals | A-11 | Substitute tool and escalation path |

### Change log

| Date | Change | Evidence (interview ID or source ID) |
|---|---|---|
| | | |
