# User Interface

Related documents: `requirements.md` (FR-22, FR-23, FR-24, C-02), `architecture.md` (ADR-007, ADR-015), `state_machine.md`, `approval_policy.md`, `interfaces.md` (HTTP API).

The course asks for an interface "designed around the actual user and workflow rather than defaulting to chat". This document shows how each screen follows from the student's work.

## Who uses which interface

| User | Interface | Why |
|---|---|---|
| **Student** (owner) | The dashboard | They run the process, watch progress, and approve consequential actions |
| **Observer** (advisor or coordinator, optional) | Read-only, redacted dashboard view | To see progress without seeing private reasons |
| **Committee members** | **Email only** | They should not need to install, learn, or log in to anything (A-03). For them, the email *is* the interface (see "Emails as an interface" below) |

## Design principles

1. **A board, not a chat.** The student's real question is "where does each person stand, and what happens next?" A board with one row per member answers that at a glance. A chat log hides it.
2. **Show state and the next step.** Every screen shows the defense state (`COLLECTING`, `AWAITING_APPROVAL`, …) and the next expected event, for example "Next: reminder to M4 on Thu 09:00".
3. **Explain every agent action.** Each automatic action shows the agent's short rationale and the deterministic checks it passed. The student can always see *why*.
4. **The student decides consequential actions on one screen.** An approval card shows exactly what will happen, the exact messages, and all checks. It has two buttons.
5. **Make uncertainty visible.** Low-confidence or unclear availability is shown differently from confirmed availability (amber and hatched), so the student never mistakes a guess for a fact.
6. **Privacy by view.** What each role sees follows the visibility table in `data_model.md`.
7. **Errors say what to do.** Every failure shown in the UI says what the system is doing about it and whether the student must act (see the error-state table below).

## Screens

| # | Screen | Student's task | What it shows | Actions | Requirements | States |
|---|---|---|---|---|---|---|
| 1 | **Setup** | Describe the defense and committee | Form: title, degree, window, attendance mode, audience; committee table (name, email, role, time zone, mandatory); policy check results next to each field | Save; run checks; preview the poll; **Start coordination** | FR-01, FR-02, FR-03 | `DRAFT` |
| 2 | **Coordination board** (home) | "Where does everyone stand?" | One row per member: role, status badge, last contact, messages sent, open issue (for example "which Tuesday?"); state banner; next scheduled event | Open member details; pause or resume the agent; cancel | FR-22, FR-23 | all |
| 3 | **Availability grid** | "Which dates are possible?" | Days × time blocks. Green = all mandatory members free and policy OK; amber = depends on pending or unclear replies; red = blocked; grey = outside the policy (notice, hours, term). Hover shows *who* blocks a cell (by name for the owner, by role for observers) | Click a cell to see the solver's reasons | FR-12 | `COLLECTING` onward |
| 4 | **Approval inbox** | "Do I agree with what the assistant proposes?" | Cards: plain-language summary, exact rendered messages, every check with ✓ or ✗, agent rationale (labelled "proposed by the assistant"), expiry time | **Approve**; **Reject with note** | FR-15, FR-18, AP rules | `AWAITING_APPROVAL`, `SCHEDULED`, `RESCHEDULING` |
| 5 | **Review queue** | "Something needs my eyes" | Quarantined messages (unknown sender, suspected injection), unreadable replies, flagged consequential statements; the raw text shown as escaped plain text | Enter availability with a structured form; release; reject | FR-07, FR-23, AP-13, AP-14 | any |
| 6 | **Member details** | "What did this person say, and what did we send?" | Message thread (owner only), extracted statements with confidence and issues, private reason (owner only), counters | Correct or add a statement by hand | FR-05, FR-23 | any |
| 7 | **Timeline** | "What happened, and when?" | The event log in order: messages, timers, tool calls, approvals, state changes | Filter by member or type | FR-25 | any |
| 8 | **Trace viewer** | "Why did the assistant do that?" | Per wake-up: the trigger event, spans for LLM and tool calls, rationale, validator results, latency, tokens, cost | Open a span | FR-25, NFR-04 | any |
| 9 | **Metrics** | "Is it working, and what does it cost?" | Success, approvals, emails per member, cost per success, latency p50/p95, errors; evaluation tables when available | — | FR-26, M-xx | — |
| 10 | **Simulation controls** (demo only) | Move time and inject events | Simulated clock; buttons +1 h, +1 day, +2 days, run to next event; preset inject events | Advance; inject | FR-24 | demo mode only |

### Board sketch

```text
┌ Defense: "Graph Methods for …" (MSc) ─ state: COLLECTING ─ sim time: Tue 10 Nov 09:00 ┐
│ Next: reminder to Dr. K (M4) Thu 12 Nov 09:00 · 1 approval waiting · 1 review item    │
├──────────────┬──────────┬─────────────────────┬─────────┬────────────────────────────┤
│ Member       │ Role     │ Status              │ Msgs    │ Open issue                 │
├──────────────┼──────────┼─────────────────────┼─────────┼────────────────────────────┤
│ Dr. A  (M1)  │ Advisor  │ ✓ Replied           │ 1       │ —                          │
│ Dr. B  (M2)  │ Internal │ ? Needs clarification│ 2      │ "Tuesday afternoon": which? │
│ Dr. C  (M3)  │ Internal │ ⏸ Deferred to 16 Nov │ 1      │ —                          │
│ Dr. K  (M4)  │ External │ … Awaiting reply    │ 2       │ 1 reminder sent            │
└──────────────┴──────────┴─────────────────────┴─────────┴────────────────────────────┘
```

Each status has a text label and an icon, not only a color.

### Approval card sketch

```text
┌ PROPOSED BY THE ASSISTANT ─ expires Thu 12 Nov 09:00 ───────────────────────────────┐
│ Book Room B-204 (hybrid, 30 seats) on Tue 24 Nov 13:00–14:30                        │
│ and email invites to 5 members (BCC).                                                │
│ Checks: ✓ all mandatory roles available  ✓ notice ≥ 14 days (ASSUMPTION value)      │
│         ✓ inside term  ✓ working hours  ✓ capacity 30 ≥ 25  ✓ hybrid needed by M4    │
│ Why: "Only slot where M2's clarified Tuesday and M4's Paris afternoon overlap."     │
│ [ Show invite text ▾ ]                                  [ Reject with note ] [ Approve ] │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## Emails as an interface (for committee members)

Committee members never see the dashboard, so the messages must be easy to answer:

- **One question per message.** For example: "Which Tuesday afternoon works for you: 17 Nov or 24 Nov?"
- **Concrete options in the member's own time zone**, rendered by code.
- **Free-text replies are accepted.** Nobody has to click a link or fill a form.
- **Short**, with a clear subject that includes the thread token, for example `[DEF-7Q2K] Defense date: one quick question`.
- **An honest footer:** sent on behalf of the student by a coordination assistant; reply to this address; contact the student directly with any concern.
- **Never** includes other members' names, availability, or reasons.

Burden is measured by emails per member (M-06). Wording quality is measured by the manual message review (`evaluation.md`).

## Empty and error states

| Situation | What the UI shows | Related failure |
|---|---|---|
| No replies yet | "Waiting for replies — first reminder on <date>" | FM-01 |
| A reply could not be read | Review item with a structured entry form | FM-12 |
| Email service down | Status bar: "Email unavailable since <time> — N messages queued" | FM-09 |
| LLM unavailable or budget reached | Banner: "Assistant paused — manual mode available" | FM-10, FM-11, FM-24 |
| Approval out of date | "This proposal is out of date because <event>. See the new proposal." | FM-17 |
| Possible attack | Review item: "Message contains instructions to the system" or "Unverified sender" | FM-20, FM-22 |
| No possible date | Escalation panel with options: extend window, remote attendance, substitute | FM-23 |
| Room lost or cancellation | Banner, plus a new proposal in the approval inbox | FM-05, FM-07 |

## Accessibility and usability basics

- Status never depends on color alone: each status has a label and an icon.
- All actions work with the keyboard. Forms have labels. Contrast is readable.
- Dates are shown with the weekday and the time zone, for example "Tue 24 Nov 13:00 (Beirut)".
- Destructive actions (cancel, reject) ask for confirmation inside the page, not with a browser pop-up.

## Usability check (SHOULD)

After ST-12, ask **2–3 graduate students** to do these 5 tasks with the demo scenario, thinking aloud:

1. Set up a defense and start coordination.
2. Find out which member is blocking the best date, and why.
3. Decide on a pending approval.
4. Handle a message in the review queue.
5. Find out why the assistant sent a clarification to M2.

For each task, record: completed (yes / with help / no), time taken, and points of confusion (paraphrased).
Save the results in `research/usability/`, and fix the top 3 problems. Report the results in the final report (UI/UX, G6).
This is also extra grounding evidence for G1.

## Out of scope

- A mobile app.
- Chat with the assistant.
- Email or push notifications to the student (the dashboard badge is enough for the MVP).
- A committee-member portal.
