"""Every dependency is pinned to one exact version (threat TH-12, bonus B-2).

Why: with "ruff>=0.16" a new release could silently change what is installed
on CI or on the grader's machine. With "ruff==0.16.9" everyone gets the same code,
and Dependabot proposes upgrades as reviewed pull requests instead.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# "name==1.2.3" or "name[extra]==1.2.3", optionally followed by "; marker".
EXACT_PIN = re.compile(r"^[A-Za-z0-9._-]+(\[[A-Za-z0-9._,-]+\])?==[A-Za-z0-9.+!-]+(\s*;.*)?$")


def unpinned(requirements: list[str]) -> list[str]:
    """Return the requirement strings that are not pinned with '=='."""
    return [req for req in requirements if not EXACT_PIN.match(req.strip())]


def load_pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def test_runtime_dependencies_are_pinned() -> None:
    project = load_pyproject()["project"]
    assert unpinned(project["dependencies"]) == []


def test_every_optional_dependency_group_is_pinned() -> None:
    groups = load_pyproject()["project"]["optional-dependencies"]
    for name, requirements in groups.items():
        assert unpinned(requirements) == [], f"group [{name}] has unpinned packages"


def test_build_backend_is_pinned() -> None:
    assert unpinned(load_pyproject()["build-system"]["requires"]) == []


def test_pin_check_rejects_loose_versions() -> None:
    # Hostile input: every common way of NOT pinning must be caught.
    loose = [
        "pydantic",
        "pydantic>=2",
        "pydantic~=2.9",
        "pydantic==2.*",
        "pydantic<3",
        "pydantic>=2,<3",
        "pydantic @ https://example.com/pydantic.whl",
    ]
    assert unpinned(loose) == loose


def test_pin_check_accepts_exact_versions() -> None:
    exact = ["ruff==0.16.9", "pydantic[email]==2.9.2", "tzdata==2026.4; sys_platform == 'win32'"]
    assert unpinned(exact) == []
