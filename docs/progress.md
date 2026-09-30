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
