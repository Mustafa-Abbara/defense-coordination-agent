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

**Not tested in the workspace (must be run by the student)**
- Windows local run; GitHub repo creation; CI green on `main`; badge; `git log` on the real repository.

**Open issues**
- README badge has a `<GITHUB_USER>` placeholder.
- Only direct dependencies are pinned; transitive dependencies are not locked (`threat_model.md` TH-12 mentions a lock file). Planned with bonus B-2 (`pip-audit`/Dependabot).
- `threat_model.md` TH-12 cites SEC-13, which is not defined in the SEC table.
- The ban covers only the four `datetime` calls named in ADR-010; `time.time()` and `datetime.fromtimestamp(time.time())` are other ways to read the real clock.
