"""Smoke tests: the project installs and the basic environment is right.

These tests prove that the tooling works before any feature exists (ST-00).
"""

import sys
from importlib.metadata import version
from zoneinfo import ZoneInfo

import app


def test_app_package_imports() -> None:
    # If this fails, the editable install (pip install -e ".[dev]") is broken.
    assert app.__doc__ is not None


def test_installed_package_version_is_readable() -> None:
    # The version comes from pyproject.toml through the installed metadata.
    assert version("defense-coordination-agent") == "0.1.0"


def test_python_is_3_12() -> None:
    # pyproject.toml requires 3.12; the project is tested only on 3.12.
    assert sys.version_info[:2] == (3, 12)


def test_iana_time_zones_are_available() -> None:
    # Windows has no built-in IANA time zone database. The tzdata package
    # provides it (ADR-012). Later stages depend on these two zones for DST tests.
    assert ZoneInfo("Europe/Paris").key == "Europe/Paris"
    assert ZoneInfo("America/New_York").key == "America/New_York"
