# config/

Checked at start-up by `app/core/config.py` (ST-02). A bad file stops the app with a
message naming the file and the field (FM-27).

| File | Schema | Used by |
|---|---|---|
| `policy.yaml` | `PolicyConfig` | policy engine, resolver, solver (ST-03) |
| `reminders.yaml` | `ReminderConfig` | reminder timers (ST-04), rate limits (ST-09) |
| `models.yaml` | `ModelsConfig` | LLM client (ST-06) |
| `solver.yaml` | `SolverConfig` | slot solver, T07 checks (ST-03); not part of the policy version |

Every value is a placeholder marked ASSUMPTION until ST-01 finds a source.
Secrets never go here: they go in `.env` (see `.env.example`).
The policy version is the SHA-256 of the policy *values*, so comments and line
endings do not change it.
