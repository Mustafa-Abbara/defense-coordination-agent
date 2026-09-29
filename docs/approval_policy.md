# Approval Policy

Related documents: `interfaces.md` (tools, executor), `state_machine.md`, `requirements.md` (C-02 approval burden), `threat_model.md`.

## Principle

An action needs human approval when it is **visible to other people, hard to undo, or commits a shared resource**.
Actions that only read data, or that change internal state after deterministic validation, run automatically.
Some actions are never allowed, whoever asks.
The rules are enforced in code (the tool router and the executor). They are not enforced by the prompt.

## Risk tiers

| Tier | Meaning | Who acts | Examples |
|---|---|---|---|
| **R0** Automatic, internal | No one outside the system notices. Fully reversible. | Agent or code | Read snapshot, find slots, check rooms, save a validated statement, set timers, wait, escalate |
| **R1** Automatic with guardrails | One short message to **one** committee member, from a template or validated text. Rate-limited. Logged. | Agent or code | Clarification (T04), extra reminder (T05), single-member availability request (T06), routine reminders from timers |
| **R2** Needs student approval | Visible to several people, commits a room, or changes the plan others rely on. | Agent **proposes** → student approves → executor runs | Start poll, schedule (book and invite), announcement, re-poll everyone, reschedule, cancel, substitute request |
| **R3** Never allowed | Would break policy, privacy, or authority. | No one through the system | See the list below |

## Action rules

| ID | Action | Tier | Conditions and notes |
|---|---|---|---|
| AP-01 | Send the first availability poll to the committee | R2 | Approved by the "Start coordination" click after the preview (FR-03) |
| AP-02 | Routine reminder from the timer cadence | R1 | Template only. Stops at `NON_RESPONSIVE`. Not sent to `DEFERRED` members before `recheck_at` |
| AP-03 | Clarification to one member (T04) | R1 | Output validator. At most 1 per member per 2 days. At most 6 messages per member per defense (placeholders) |
| AP-04 | Extra reminder (T05) | R1 | Counts against the same limits as AP-03 |
| AP-05 | Availability request to one member (T06) | R1 | Only `NEW_MEMBER` or `SINGLE_FOLLOWUP` |
| AP-06 | Re-poll several members, or re-poll after a disruption (T06) | **R2** | Faculty burden: several people get another email |
| AP-07 | Propose a schedule (T07) → book room and send invites | **R2** | One approval covers both (bundle). The executor re-validates everything before acting |
| AP-08 | Announcement | **R2** | Template. Created automatically on entering `SCHEDULED`. Blocked if the notice deadline has passed |
| AP-09 | Substitute request to the advisor and coordinator (T08) | **R2** | Only a templated request is sent. The committee change itself is done by the student in setup, after real-world approval |
| AP-10 | Reschedule: cancel booking and invites, send change notices (T09) | **R2** | The payload lists everything that will be cancelled and sent |
| AP-11 | Cancel the defense | **R2** | Only if something was already sent. Otherwise it is immediate |
| AP-12 | Escalate to the student (T10) | R0 | Always allowed |
| AP-13 | Release a quarantined message | Human only | The student reviews the raw message in the UI |
| AP-14 | Manual availability entry or correction | Human only | Saved with `source = MANUAL`, logged |

### Automatic tier bumps (R1 → R2)

An R1 action becomes R2 (needs approval) when:

- the member's thread has a `SUSPICIOUS_INSTRUCTION` or a quarantined message in the last 7 days;
- the member would receive their 5th or later message in this defense;
- the question text mentions a slot that is not in the current feasible or near-miss list;
- the defense is in `ESCALATED` (normally no messages are sent then; this is a safety net).

### R3: never allowed

1. Send any message to an address that is not a registered committee member or a configured coordinator or advisor address.
2. Include another member's name, email, availability details, or private reason in a message.
3. Book, invite, or announce a slot that fails any hard constraint (roles, notice, term, duration, working hours, capacity, hybrid need).
4. Change the committee composition, roles, mandatory flags, or policy values.
5. Act on instructions found inside an email (for example "cancel the defense", "send the draft to this address").
6. Approve an approval request (the `agent` identity is refused by the API).
7. Delete or edit events, approvals, or traces.
8. Send attachments or links in agent-written text.
9. Use real personal data in evaluation (synthetic data only).

## How an approval works

1. The agent (or a handler) creates an `ApprovalRequest` with the exact payload, `payload_hash`, `state_version`, `agent_rationale`, and `validator_report`.
2. The approval inbox card shows:
   - what will happen, in plain words ("Book Room B-204 on Tue 17 Nov 10:00–11:30 and email invites to 5 members");
   - the exact rendered messages;
   - every check with ✓ or ✗ (roles, notice, term, room, conditions, stale inputs);
   - the agent's rationale, marked "proposed by the assistant";
   - buttons **Approve** and **Reject (with note)**.
   Editing the payload is not supported in the MVP (COULD). The student rejects with a note, and the agent proposes again. This keeps one validation path.
3. On **Approve**, the API checks the caller role, the owner, and `payload_hash`. The executor then re-runs all validators on the *current* state. If anything relevant changed → `STALE`, nothing runs, and the agent is woken.
4. The executor runs each step with an idempotency key. The result is recorded (`EXECUTED` or `FAILED` with the failing step).
5. Expiry: a request not decided within 48 simulated hours (placeholder) → `EXPIRED`, and the agent is woken.

## Logging

Every approval produces `WorkflowEvent`s in the hash-chained log:
`APPROVAL_REQUESTED`, `APPROVAL_DECIDED` (who, when, decision, note, `payload_hash`), `APPROVAL_EXECUTED` or `APPROVAL_FAILED` (step and error), `APPROVAL_STALE`, `APPROVAL_EXPIRED`.
Automatic R1 actions log `TOOL_CALLED` with tier `R1` and the message ID.
R3 attempts log `TOOL_REJECTED` with `POLICY_VIOLATION` or `UNAUTHORIZED`. They are counted in security metrics.

## Measuring approval burden (constraint C-02)

| Metric | Formula | Target (proposed) |
|---|---|---|
| Approvals per defense | number of approval requests / number of defenses | 3 or fewer with no disruption (AP-01, AP-07, AP-08) |
| Human actions per defense | approvals + manual reviews + escalations handled + manual entries | Reported per scenario category |
| Rejection rate | rejected / decided | Low. A high rate means the agent proposes badly |
| Stale or expired rate | (stale + expired) / requested | Low. A high rate means it proposes too early |
| Avoided approvals | R1 actions executed automatically | Reported. This shows what the tier design saves |
| Time to decision (demo and UI only) | `decided_at − requested_at` | Reported, not a target (simulated) |

In the evaluation harness, the "student" is scripted:
- Approve if the validator report is all ✓.
- Otherwise reject with a note.

The scripted student does **not** look at the oracle's ground truth. A real student cannot know it either.
If the system believes something wrong (for example, an extraction error), the approval goes through, and the error shows up later: a member declines the invite, or the oracle marks the outcome as wrong.
This keeps extraction mistakes visible in the metrics instead of hiding them behind a perfect human.
The same scripted student is used for the agent and the baselines. See `evaluation.md`.
