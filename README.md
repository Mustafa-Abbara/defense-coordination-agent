# Thesis Defense Coordination Agent

[![CI](https://github.com/Mustafa-Abbara/defense-coordination-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Mustafa-Abbara/defense-coordination-agent/actions/workflows/ci.yml)

Agentic Systems 503N/798S, Fall 2026, Path A. One orchestrating agent, deterministic
services, and human approval coordinate a thesis defense from the first availability
request to the confirmed booking and announcement.

**Status:** ST-02 (domain models, configuration, state machines). No agent features yet.
The design documents are in [`docs/`](docs/README.md); the build plan is
[`docs/roadmap.md`](docs/roadmap.md); progress is in [`docs/progress.md`](docs/progress.md).

## Quick start (Windows, PowerShell, no Docker)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy .env.example .env      # fill in values later; .env is never committed
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Linux/macOS: the same, with `python3.12 -m venv .venv` and `source .venv/bin/activate`.

## Rules enforced from day one

- **Simulated clock (ADR-010):** `datetime.now()`, `datetime.utcnow()`, `datetime.today()`
  and `date.today()` fail lint (Ruff rule TID251) everywhere except `app/adapters/clock.py`.
- **Secrets (TH-08):** only in `.env` (ignored by git). `.env.example` has names, no values.
- **CI:** lint, format check, and tests on `ubuntu-latest` and `windows-latest`.

The full quick start, demo, and reproduction instructions come in ST-19.
