"""The lint rule for ADR-010 really works.

ADR-010: code must get time from the Clock interface, never from the real
system clock. Ruff rule TID251 (banned API) enforces this. These tests run the
real Ruff, with the real pyproject.toml, on small code samples, and check which
samples are reported.

How: Ruff reads the code from standard input and we tell it which file name to
pretend the code has (--stdin-filename). This lets us test "the same code" in
two places without creating any files in the repository.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOCK_FILE = "app/adapters/clock.py"
OTHER_FILE = "app/services/some_module.py"


def tid251_violations(source: str, pretend_path: str) -> list[dict]:
    """Run Ruff on `source` as if it lived at `pretend_path`; return TID251 reports."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "TID251",
            "--output-format",
            "json",
            "--stdin-filename",
            pretend_path,
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,  # so Ruff uses this repository's pyproject.toml
        timeout=60,
        check=False,  # Ruff exits with 1 when it finds problems; that is expected
    )
    # Exit code 2 means Ruff itself failed (bad config, crash): fail loudly.
    assert result.returncode in (0, 1), result.stderr
    reports = json.loads(result.stdout)
    return [r for r in reports if r["code"] == "TID251"]


# Each sample calls the real clock in a different way.
BANNED_SAMPLES = {
    "direct": "import datetime\n\nx = datetime.datetime.now()\n",
    "from_import": "from datetime import datetime\n\nx = datetime.now()\n",
    "alias": "from datetime import datetime as dt\n\nx = dt.now()\n",
    "module_alias": "import datetime as d\n\nx = d.datetime.now()\n",
    "utcnow": "from datetime import datetime\n\nx = datetime.utcnow()\n",
    "datetime_today": "from datetime import datetime\n\nx = datetime.today()\n",
    "date_today": "from datetime import date\n\nx = date.today()\n",
    "date_alias_today": "from datetime import date as day\n\nx = day.today()\n",
}


@pytest.mark.parametrize("name", sorted(BANNED_SAMPLES))
def test_real_clock_call_is_reported_outside_clock_adapter(name: str) -> None:
    violations = tid251_violations(BANNED_SAMPLES[name], OTHER_FILE)
    assert len(violations) == 1, f"sample {name!r} was not reported"
    assert "ADR-010" in violations[0]["message"]


@pytest.mark.parametrize("name", sorted(BANNED_SAMPLES))
def test_same_call_is_allowed_in_clock_adapter(name: str) -> None:
    assert tid251_violations(BANNED_SAMPLES[name], CLOCK_FILE) == []


def test_rule_also_applies_to_test_files() -> None:
    # "Everywhere except app/adapters/clock.py" includes the tests.
    source = BANNED_SAMPLES["alias"]
    assert len(tid251_violations(source, "tests/unit/test_example.py")) == 1


def test_a_file_named_clock_elsewhere_is_not_exempt() -> None:
    # Hostile case: someone names a file clock.py in another folder to dodge the rule.
    source = BANNED_SAMPLES["direct"]
    assert len(tid251_violations(source, "app/services/clock.py")) == 1


def test_building_a_fixed_datetime_is_allowed() -> None:
    # Fixed, timezone-aware datetimes are fine: they do not read the real clock.
    source = (
        "from datetime import UTC, datetime, timedelta\n\n"
        "start = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)\n"
        "later = start + timedelta(days=3)\n"
    )
    assert tid251_violations(source, OTHER_FILE) == []
