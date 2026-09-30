# Progress Log

One entry per finished stage (see `roadmap.md`). The next session starts from here.
Status words: **implemented** (code exists), **tested** (automated test passes),
**manually verified** (a person checked it), **assumed**, **not implemented**.

---

## ST-00 Repository and tooling foundation (29 Sep 2026)

**Built**
- Repository layout from `architecture.md` (`app/` subpackages, `eval/`, `tests/{unit,integration,failure,security}`, `config/`, `research/`, `docs/`).
- `pyproject.toml`: Python 3.12, exact pins (`tzdata==2026.4`; dev: `pytest==9.1.1`, `pytest-cov==7.1.0`, `ruff==0.16.9`; build: `setuptools==84.0.0`).
- Ruff config (rules E, W, F, I, B, UP, DTZ, TID); TID251 bans `datetime.datetime.now/utcnow/today` and `datetime.date.today`, exempt only in `app/adapters/clock.py` (ADR-010). `docs/` excluded from Ruff (pseudocode).
- pytest and coverage config.
- `.gitignore` (`.env`, `*.db`, caches, venv), `.env.example` (no values), `.gitattributes` (LF endings everywhere, so later file hashes match across OSes).
- `.github/workflows/ci.yml`: lint, format check, tests on `ubuntu-latest` and `windows-latest`, Python 3.12, full history checkout, read-only permissions.
- Tests: `tests/unit/test_smoke.py` (4), `tests/unit/test_banned_time_api.py` (19), `tests/security/test_repo_hygiene.py` (4).

**Results in the build workspace (Linux, Python 3.12.3)**
- `ruff check .` → All checks passed. `ruff format --check .` → 18 files already formatted. `pytest` → 27 passed.
- Negative checks: a real file calling `dt.now()` in `app/services/` → TID251 reported (exit 1); a repo where `.env` was committed then removed → `test_no_env_file_ever_committed` fails.

**Verified after delivery (30 Sep 2026)**
- Windows, Python 3.12.6: `ruff check .` → All checks passed; `ruff format --check .` → 19 files already formatted; `pytest` → 32 passed (run during B-2).
- GitHub repo `Mustafa-Abbara/defense-coordination-agent` created; CI green on `ubuntu-latest` and `windows-latest` for every merged PR (#1, #2); `main` protected by ruleset `protect-main` (required checks: both CI jobs, gitleaks, pip-audit).
- No `.env` ever committed: `test_no_env_file_ever_committed` runs in CI with full history (`fetch-depth: 0`) and passes.
- **All ST-00 acceptance criteria: PASS.**

**Open issues**
- README badge has a `<GITHUB_USER>` placeholder. → Fixed (30 Sep).
- Only direct dependencies are pinned; transitive dependencies are not locked (`threat_model.md` TH-12 mentions a lock file). B-2 added scanning, not a lock file → still open.
- `threat_model.md` TH-12 cites SEC-13, which is not defined in the SEC table. → Defined in B-2.
- The ban covers only the four `datetime` calls named in ADR-010; `time.time()` and `datetime.fromtimestamp(time.time())` are other ways to read the real clock.

---

## B-2 Secret scanning + dependency scanning (30 Sep 2026)

**Built**
- `.github/workflows/security.yml`: job `secret scan (gitleaks)` (gitleaks 8.30.1, downloaded with SHA-256 check, full history, `--redact`) and job `dependency audit (pip-audit)`; runs on push, pull request, weekly (Mon 05:17 UTC), and on demand.
- `.gitleaks.toml`: default rules plus one allowlist entry for the exact fake key in `test_repo_hygiene.py` (found by gitleaks on the first local scan).
- `.github/dependabot.yml`: weekly update PRs for pip (`pyproject.toml`) and GitHub Actions.
- `pyproject.toml`: `pip-audit==2.10.1` added to `[dev]`.
- `tests/security/test_dependency_pins.py` (5 tests, SEC-13): every dependency pinned with `==`; loose versions rejected.
- Docs: `threat_model.md` (TH-08/TH-12 controls, new SEC-13 row, "Repository checks" section), `architecture.md` (pip-audit in supporting libraries).

**Results in the build workspace (Linux, Python 3.12.3)**
- `ruff check .` → All checks passed. `ruff format --check .` → 19 files already formatted. `pytest` → 32 passed.
- `python -m pip_audit --skip-editable` → No known vulnerabilities found (own package skipped as editable).
- gitleaks on the repo: no leaks. gitleaks on a copy with a fake `ghp_…` token committed: 1 leak (`github-pat`), exit 1.

**Evidence on GitHub (30 Sep 2026)** — screenshots in `Project/evidence/` (outside the repo)
- PR #1 (B-2) merged with all required checks green.
- Demo PR #4 (`demo-fake-secret`, random fake `ghp_…` token): `secret scan (gitleaks)` failed (`RuleID: github-pat`, `Secret: REDACTED`, `leaks found: 1`, exit 1); merge blocked by the required check; PR closed unmerged and branch deleted. Screenshots: `PR_page.png`, `job_log.png`.
- Dependabot PR #2 (`actions/checkout` 6→7) reviewed and merged, 8/8 checks passed. Screenshot: `b2_dependabot_pr2_merged.png`. Dependabot PR #3 (`actions/setup-python` 6→7) also merged (`main` now uses `setup-python@v7`).
- `protect-main` requires: `lint + tests (ubuntu-latest)`, `lint + tests (windows-latest)`, `secret scan (gitleaks)`, `dependency audit (pip-audit)`.
- **B-2 bonus evidence complete** (roadmap points 1–4).

**Fix found during the demo**
- The job log showed gitleaks scanning every fetched branch (no `--log-opts`). While a leaking branch exists on GitHub, runs on *other* branches would also fail. Fixed: `--log-opts="HEAD"` (scan the history of the commit under test). Verified locally: `main` passes while a leaking branch exists; the leaking branch fails.

**Open issues**
- Indirect dependencies are not locked (no lock file); pip-audit still audits them.

---

## ST-02 Domain models, configuration, and state machine table (30 Sep 2026)

**Built**
- `app/core/enums.py`: every enum in `data_model.md`, plus `DefenseEvent` and `MemberEvent`.
- `app/core/fields.py`: `StrictModel` base (`extra="forbid"`, `validate_assignment`, `hide_input_in_errors`); checked types `UtcDatetime` (naive rejected, stored in UTC), `IanaTimeZone`, `MemberAlias` (`M1`–`M7`), `Sha256Hex`, `EntityId`.
- `app/core/models.py`: `Slot`, `Defense`, `CommitteeMember`, `AvailabilityStatement`, `Room`, `Booking`, `Message`, `ApprovalRequest`, `Timer`, `WorkflowEvent`, `TraceSpan`, `User`. PII and restricted fields are `repr=False`.
- `app/core/state_machine.py`: `DEFENSE_TRANSITIONS` (37 rows + RESUME), `MEMBER_TRANSITIONS` (30 rows), `transition()`, `member_transition()`, `IllegalTransitionError` (logged). Raw strings are refused (`TypeError`).
- `app/core/hashing.py`: `canonical_json`, `sha256_hex`.
- `app/core/config.py`: `Settings` (pydantic-settings, `.env`), `PolicyConfig`, `ReminderConfig`, `ModelsConfig`, `AppConfig`, `load_app_config()`, `policy_version()` (sha256 of the canonical JSON of the values), `ConfigError`. YAML is read with a SafeLoader subclass that also refuses duplicate keys.
- `config/policy.yaml`, `config/reminders.yaml`, `config/models.yaml` (all values ASSUMPTION or TO BE DECIDED).
- `pyproject.toml`: `pydantic==2.13.5`, `pydantic-settings==2.15.0`, `PyYAML==6.0.3`, `email-validator==2.3.0` (versions: latest on PyPI via `pip index versions`, 30 Sep 2026).
- `.env.example`: `APP_ENV`, `DEMO_MODE=false`, `LLM_API_KEY=`, `CONFIG_DIR`.
- Tests: `tests/unit/test_state_machine.py`, `test_models.py`, `test_config.py`, `test_hashing.py`, `conftest.py` (305 new tests, 337 total, after the Windows fix below).
- Docs: `state_machine.md` (new "Transition tables" section), `data_model.md` (`previous_status`, `TRUNCATED`, `Slot`, policy-version rule, optional `thread_token`, reminders/models/.env schemas), `failure_matrix.md` (FM-27), `config/README.md`, `README.md` status.

**Results in the build workspace (Linux, Python 3.12.3)**
- `ruff check .` → All checks passed. `ruff format --check .` → 30 files already formatted. `pytest` → 333 passed.
- Coverage of `app/core`: 99% (2 lines not covered: the default `Settings()` path and a YAML error without a line mark).
- `python -m pip_audit --skip-editable` → No known vulnerabilities found.
- Time zone tests also pass with `PYTHONTZPATH=""` (no system zone database, as on Windows).
- Mutation check: 10 deliberate bugs (drop a row, add an illegal row, remove the enum type check, weaken resume, `extra="ignore"`, show input in errors, plain SafeLoader, hash `repr` instead of canonical JSON, email in repr, `DEMO_MODE` default true) → each one makes at least one test fail.

**Bug found and fixed:** a YAML list used as a key crashed with a raw `TypeError` instead of `ConfigError`. Regression test `test_list_used_as_a_key_is_rejected`; new row FM-27.

**Fix found on Windows (30 Sep 2026)**
- First Windows run: 332 passed, 1 failed: `test_invalid_time_zone_is_rejected[CET ]`. Cause: `ZoneInfo(name)` opens a file named after the zone, and Windows file names ignore trailing spaces and case, so `"CET "` (and `"asia/beirut"`) were accepted on Windows but refused on Linux.
- Fix: `app/core/fields.py` now checks the name against the exact list `zoneinfo.available_timezones()` (minus the machine-specific `localtime`). Same result on every OS.
- Regression cases added: `"Asia/Beirut "`, `"asia/beirut"`, `"ASIA/BEIRUT"`, `"localtime"`. Workspace: 337 passed (also with `PYTHONTZPATH=""`).

**Fix found by CI (30 Sep 2026)**
- `secret scan (gitleaks)` failed on the ST-02 pull request: rule `generic-api-key` matched the deliberately fake key `sk-live-CANARY-7F3A` in `tests/unit/test_config.py` (`test_api_key_is_hidden_in_repr_and_dump`). Cause: I did not run gitleaks on the new files before delivery.
- Fix: that exact string added to the allowlist in `.gitleaks.toml` (same pattern as B-2); `threat_model.md` updated. Verified with gitleaks 8.30.1 on a scratch repository: the ST-02 commit passes (exit 0); a different fake key still fails (exit 1).
- Also re-delivered `tests/unit/test_config.py`: the Windows-path fix for `test_unsafe_yaml_tag_is_rejected` had not reached the repository.
- From now on, gitleaks is part of the verification step of every stage.

**Verified after delivery (30 Sep 2026)** — reported by me (the student); the full logs are on GitHub in the checks of the ST-02 pull request.
- Windows, Python 3.12.6: `ruff check .` → All checks passed; `ruff format --check .` → 30 files already formatted; `pytest` → 337 passed.
- ST-02 pull request: all 4 required checks green (`lint + tests (ubuntu-latest)`, `lint + tests (windows-latest)`, `secret scan (gitleaks)`, `dependency audit (pip-audit)`); merged into `main`; CI on `main` green.
- **All ST-02 acceptance criteria: PASS**, on Linux, on Windows, and in CI.

**Open issues**
- Member transitions not yet in the table (by design, doc lists them): clarification to a non-`NEEDS_CLARIFICATION` member (T04), second reply from a `REPLIED` member, early reply from a `DEFERRED` member, re-invites/re-polls after a reschedule. Owners: ST-08, ST-09, ST-11, ST-13.
- `Message` has no timestamp field, but deduplication "within 24 h" (pipeline stage 2) needs one → ST-08.
- Config values not yet in any file: confidence threshold 0.7, staleness 10 days, approval expiry 48 h, `max_wait` 3 days, step budget 8, extraction cap 10/day, body cap 4,000, budget caps → the stage that uses each adds it (with a doc edit).
- `models.yaml` prices are 0 until the provider is chosen (ST-06).
