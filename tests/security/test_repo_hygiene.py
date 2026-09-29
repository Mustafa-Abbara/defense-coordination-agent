"""Secrets stay out of git (threat TH-08, first part of SEC-10).

SEC-10 as a whole is finished in later stages (logs, traces, error pages).
Here we check the repository rules that exist from day one:
  - .gitignore ignores .env and database files;
  - .env.example contains no secret values;
  - no file named .env was ever committed (when run inside a git repository).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# A variable whose name contains one of these words is treated as a secret.
SECRET_NAME_WORDS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def filled_secret_names(env_text: str) -> list[str]:
    """Return the names of secret-looking variables that have a value.

    Blank lines and comments are ignored. "LLM_API_KEY=" is fine (empty);
    "LLM_API_KEY=sk-123" is reported.
    """
    found = []
    for raw_line in env_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().upper()
        value = value.strip().strip('"').strip("'")
        if value and any(word in name for word in SECRET_NAME_WORDS):
            found.append(name)
    return found


def read_repo_file(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_gitignore_ignores_env_and_databases() -> None:
    lines = {line.strip() for line in read_repo_file(".gitignore").splitlines()}
    assert ".env" in lines
    assert "*.db" in lines


def test_env_example_exists_and_has_no_secret_values() -> None:
    assert filled_secret_names(read_repo_file(".env.example")) == []


def test_secret_check_catches_a_filled_key() -> None:
    # Hostile input: a real-looking key pasted into the example file.
    text = (
        "# comment\n"
        "LLM_API_KEY=sk-live-1234567890\n"
        'SESSION_SECRET="abc"\n'
        "APP_ENV=dev\n"
        "ADMIN_PASSWORD=\n"
    )
    assert filled_secret_names(text) == ["LLM_API_KEY", "SESSION_SECRET"]


def _inside_git_repo() -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


@pytest.mark.skipif(not _inside_git_repo(), reason="not inside a git repository")
def test_no_env_file_ever_committed() -> None:
    # Lists every path touched by every commit on every branch.
    # CI checks out the full history (fetch-depth: 0) so this sees all commits.
    result = subprocess.run(
        ["git", "log", "--all", "--name-only", "--format="],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    committed_env_files = [
        path for path in result.stdout.splitlines() if Path(path.strip()).name == ".env"
    ]
    assert committed_env_files == []
