"""Configuration loading: YAML files and .env settings (ST-02).

Config files are edited by hand, so every mistake must fail loudly, at start-up,
with a message that names the file and the field.
"""

from pathlib import Path

import pytest
import yaml

from app.core.config import (
    AppConfig,
    ConfigError,
    PolicyConfig,
    Settings,
    load_app_config,
    load_models,
    load_policy,
    load_reminders,
    policy_version,
)
from app.core.enums import DegreeLevel

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
POLICY_TEXT = (CONFIG_DIR / "policy.yaml").read_text(encoding="utf-8")


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))  # bytes: keep line endings exactly as given
    return path


def policy_dict() -> dict:
    return yaml.safe_load(POLICY_TEXT)


def write_policy(tmp_path: Path, data: dict) -> Path:
    return write(tmp_path, "policy.yaml", yaml.safe_dump(data, sort_keys=False))


# ---------------------------------------------------------------- the real files


def test_repository_config_files_load() -> None:
    app_config = load_app_config(Settings(_env_file=None, config_dir=CONFIG_DIR))
    assert isinstance(app_config, AppConfig)
    assert app_config.policy.notice_days >= 0
    assert set(app_config.policy.duration_minutes) == set(DegreeLevel)
    assert len(app_config.policy_version) == 64


def test_repository_policy_is_marked_as_assumption() -> None:
    # Until ST-01 collects sources, the policy must say it is a placeholder.
    assert "ASSUMPTION" in load_policy(CONFIG_DIR / "policy.yaml").status


# -------------------------------------------------- missing or wrong fields (acceptance #3)


def test_missing_policy_field_fails_with_clear_message(tmp_path: Path) -> None:
    data = policy_dict()
    del data["notice_days"]
    path = write_policy(tmp_path, data)
    with pytest.raises(ConfigError) as caught:
        load_policy(path)
    message = str(caught.value)
    assert "policy.yaml" in message
    assert "notice_days" in message
    assert "missing" in message.lower()


def test_missing_nested_field_names_the_full_path(tmp_path: Path) -> None:
    data = policy_dict()
    del data["working_hours"]["end"]
    with pytest.raises(ConfigError, match=r"working_hours\.end"):
        load_policy(write_policy(tmp_path, data))


def test_misspelled_policy_field_is_rejected(tmp_path: Path) -> None:
    data = policy_dict()
    data["notice_day"] = data.pop("notice_days")  # typo
    with pytest.raises(ConfigError) as caught:
        load_policy(write_policy(tmp_path, data))
    assert "notice_day" in str(caught.value)
    assert "not allowed" in str(caught.value).lower()


def test_wrong_type_is_rejected(tmp_path: Path) -> None:
    data = policy_dict()
    data["notice_days"] = "two weeks"
    with pytest.raises(ConfigError, match="notice_days"):
        load_policy(write_policy(tmp_path, data))


def test_negative_notice_days_is_rejected(tmp_path: Path) -> None:
    data = policy_dict()
    data["notice_days"] = -1
    with pytest.raises(ConfigError, match="notice_days"):
        load_policy(write_policy(tmp_path, data))


def test_every_degree_level_needs_a_duration(tmp_path: Path) -> None:
    data = policy_dict()
    del data["duration_minutes"]["PHD"]
    with pytest.raises(ConfigError, match="PHD"):
        load_policy(write_policy(tmp_path, data))


def test_unknown_role_is_rejected(tmp_path: Path) -> None:
    data = policy_dict()
    data["required_roles"]["MSC"] = ["ADVISOR", "DEAN"]
    with pytest.raises(ConfigError, match="required_roles"):
        load_policy(write_policy(tmp_path, data))


def test_working_hours_must_end_after_they_start(tmp_path: Path) -> None:
    data = policy_dict()
    data["working_hours"]["start"] = "18:00"
    data["working_hours"]["end"] = "08:00"
    with pytest.raises(ConfigError, match="working_hours"):
        load_policy(write_policy(tmp_path, data))


def test_term_window_must_end_after_it_starts(tmp_path: Path) -> None:
    data = policy_dict()
    data["term_windows"] = [{"start": "2026-12-20", "end": "2026-09-01"}]
    with pytest.raises(ConfigError, match="term_windows"):
        load_policy(write_policy(tmp_path, data))


def test_weekdays_must_not_repeat(tmp_path: Path) -> None:
    data = policy_dict()
    data["working_hours"]["weekdays"] = ["MON", "MON"]
    with pytest.raises(ConfigError, match="weekdays must not repeat"):
        load_policy(write_policy(tmp_path, data))


def test_part_of_day_range_must_end_after_it_starts(tmp_path: Path) -> None:
    data = policy_dict()
    data["part_of_day"]["MORNING"] = ["12:00", "08:00"]
    with pytest.raises(ConfigError, match="MORNING"):
        load_policy(write_policy(tmp_path, data))


def test_part_of_day_needs_morning_afternoon_and_evening(tmp_path: Path) -> None:
    data = policy_dict()
    del data["part_of_day"]["EVENING"]
    with pytest.raises(ConfigError, match="EVENING"):
        load_policy(write_policy(tmp_path, data))


# ---------------------------------------------------------------- broken or hostile files


def test_missing_file_gives_clear_message(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_policy(tmp_path / "policy.yaml")


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mapping"):
        load_policy(write(tmp_path, "policy.yaml", ""))


def test_top_level_list_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mapping"):
        load_policy(write(tmp_path, "policy.yaml", "- notice_days: 14\n"))


def test_invalid_yaml_syntax_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="policy.yaml"):
        load_policy(write(tmp_path, "policy.yaml", "notice_days: [14\n"))


def test_non_utf8_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_bytes(b"policy_id: \xff\xfe\n")
    with pytest.raises(ConfigError, match="UTF-8"):
        load_policy(path)


def test_list_used_as_a_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="policy.yaml"):
        load_policy(write(tmp_path, "policy.yaml", "? [a, b]\n: 1\n"))


def test_duplicate_key_is_rejected(tmp_path: Path) -> None:
    # Plain YAML silently keeps the last value. For a policy that is dangerous.
    text = POLICY_TEXT + "\nnotice_days: 1\n"
    with pytest.raises(ConfigError, match="duplicate key 'notice_days'"):
        load_policy(write(tmp_path, "policy.yaml", text))


def test_unsafe_yaml_tag_is_rejected(tmp_path: Path) -> None:
    # Hostile input: yaml.load (unsafe) would run this command. safe_load refuses.
    marker = tmp_path / "pwned.txt"
    text = f'notice_days: !!python/object/apply:os.system ["echo pwned > {marker}"]\n'
    with pytest.raises(ConfigError):
        load_policy(write(tmp_path, "policy.yaml", text))
    assert not marker.exists()


# ---------------------------------------------------------------- policy version


def test_policy_version_is_64_hex_and_stable() -> None:
    policy = load_policy(CONFIG_DIR / "policy.yaml")
    first = policy_version(policy)
    assert len(first) == 64
    assert set(first) <= set("0123456789abcdef")
    assert policy_version(load_policy(CONFIG_DIR / "policy.yaml")) == first


def test_policy_version_ignores_comments_and_line_endings(tmp_path: Path) -> None:
    original = load_policy(CONFIG_DIR / "policy.yaml")
    windows_copy = "# edited on Windows\n" + POLICY_TEXT.replace("\n", "\r\n")
    copy = load_policy(write(tmp_path, "policy.yaml", windows_copy))
    assert policy_version(copy) == policy_version(original)


def test_policy_version_changes_when_a_value_changes(tmp_path: Path) -> None:
    data = policy_dict()
    data["notice_days"] = data["notice_days"] + 1
    changed = load_policy(write_policy(tmp_path, data))
    assert policy_version(changed) != policy_version(load_policy(CONFIG_DIR / "policy.yaml"))


def test_policy_version_does_not_depend_on_key_order(tmp_path: Path) -> None:
    data = policy_dict()

    def reverse_keys(value: object) -> object:
        # Reverse the key order at every level, including nested maps such as
        # duration_minutes {PHD, MSC} and part_of_day.
        if isinstance(value, dict):
            return {key: reverse_keys(value[key]) for key in reversed(list(value))}
        return value

    reordered = load_policy(write_policy(tmp_path, reverse_keys(data)))
    assert list(reordered.duration_minutes) != list(PolicyConfig(**data).duration_minutes)
    assert policy_version(reordered) == policy_version(PolicyConfig(**data))


# ---------------------------------------------------------------- reminders and models files


def test_reminder_config_rejects_zero_day_cadence(tmp_path: Path) -> None:
    data = yaml.safe_load((CONFIG_DIR / "reminders.yaml").read_text(encoding="utf-8"))
    data["first_reminder_after_days"] = 0
    path = write(tmp_path, "reminders.yaml", yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="reminders.yaml"):
        load_reminders(path)


def test_models_config_rejects_missing_call(tmp_path: Path) -> None:
    data = yaml.safe_load((CONFIG_DIR / "models.yaml").read_text(encoding="utf-8"))
    del data["calls"]["planner"]
    path = write(tmp_path, "models.yaml", yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="planner"):
        load_models(path)


def test_models_config_rejects_negative_price(tmp_path: Path) -> None:
    data = yaml.safe_load((CONFIG_DIR / "models.yaml").read_text(encoding="utf-8"))
    data["calls"]["extractor"]["price_in_usd_per_million_tokens"] = -1
    path = write(tmp_path, "models.yaml", yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="price_in_usd_per_million_tokens"):
        load_models(path)


# ---------------------------------------------------------------- .env settings (TH-05, TH-08)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "DEMO_MODE", "LLM_API_KEY", "CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)


def test_settings_defaults_are_safe(clean_env: None) -> None:
    settings = Settings(_env_file=None)
    assert settings.demo_mode is False  # simulation endpoints off unless asked for
    assert settings.llm_api_key is None
    assert settings.app_env == "dev"


def test_settings_are_read_from_env_file(tmp_path: Path, clean_env: None) -> None:
    env_file = write(tmp_path, ".env", "APP_ENV=test\nDEMO_MODE=true\nLLM_API_KEY=sk-test-123\n")
    settings = Settings(_env_file=env_file)
    assert settings.app_env == "test"
    assert settings.demo_mode is True
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test-123"


def test_unknown_variable_in_env_file_is_rejected(tmp_path: Path, clean_env: None) -> None:
    # A typo such as LLM_APIKEY would otherwise be ignored and the key missing.
    env_file = write(tmp_path, ".env", "LLM_APIKEY=sk-test-123\n")
    with pytest.raises(ValueError, match="llm_apikey") as caught:
        Settings(_env_file=env_file)
    assert "sk-test-123" not in str(caught.value)  # the error never repeats the secret


def test_unknown_app_env_is_rejected(tmp_path: Path, clean_env: None) -> None:
    env_file = write(tmp_path, ".env", "APP_ENV=production-please\n")
    with pytest.raises(ValueError):
        Settings(_env_file=env_file)


def test_empty_api_key_means_no_key(tmp_path: Path, clean_env: None) -> None:
    env_file = write(tmp_path, ".env", "LLM_API_KEY=\n")
    assert Settings(_env_file=env_file).llm_api_key is None


def test_api_key_is_hidden_in_repr_and_dump(tmp_path: Path, clean_env: None) -> None:
    env_file = write(tmp_path, ".env", "LLM_API_KEY=sk-live-CANARY-7F3A\n")
    settings = Settings(_env_file=env_file)
    assert "CANARY-7F3A" not in repr(settings)
    assert "CANARY-7F3A" not in str(settings.model_dump())
    assert "CANARY-7F3A" not in settings.model_dump_json()


def test_env_example_lists_exactly_the_settings(clean_env: None) -> None:
    # .env.example documents every setting, and nothing else (no drift).
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    names = {
        line.split("=", 1)[0].strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert names == set(Settings.model_fields)
    Settings(_env_file=REPO_ROOT / ".env.example")  # and the example itself is valid
