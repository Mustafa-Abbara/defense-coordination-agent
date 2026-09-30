"""Central configuration (ST-02).

Two sources, both read once at start-up:

1. `.env` (secrets and switches) -> `Settings`, via pydantic-settings.
   Secrets live only here (TH-08). `.env` is never committed.
2. YAML files in `config/` (policy, reminders, models) -> checked models.
   Every value in them is a placeholder marked ASSUMPTION until ST-01 finds a source.

Any mistake (missing field, typo, wrong type, duplicate key, unsafe YAML)
raises ConfigError with a message that names the file and the field.
"""

from collections.abc import Hashable
from datetime import date, time
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import DegreeLevel, PartOfDay, Role, SubstituteApprover, Weekday
from app.core.fields import Sha256Hex, StrictModel
from app.core.hashing import canonical_json, sha256_hex


class ConfigError(Exception):
    """A configuration file is missing or invalid. The message says where and why."""


# ---------------------------------------------------------------- .env settings


class Settings(BaseSettings):
    """Values from environment variables or `.env`. Names are case-insensitive.

    Every field here must also be listed (without a secret value) in .env.example;
    a test checks this.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",  # a typo such as LLM_APIKEY fails instead of being ignored
        hide_input_in_errors=True,  # never repeat a secret value in an error
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    # Simulation controls (/api/sim/*) exist only when this is true (TH-05, SEC-07).
    # Safe default: off.
    demo_mode: bool = False
    # SecretStr prints as '**********' in repr, str, and model_dump (TH-08).
    llm_api_key: SecretStr | None = None
    config_dir: Path = Path("config")

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _empty_key_means_no_key(cls, value: Any) -> Any:
        # "LLM_API_KEY=" in .env.example means "not set", not "an empty key".
        if value == "":
            return None
        return value


# ---------------------------------------------------------------- YAML schemas


class ConfigModel(StrictModel):
    """Base for config file schemas. Frozen: config cannot be changed while running."""

    model_config = ConfigDict(frozen=True)


class DateWindow(ConfigModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class WorkingHours(ConfigModel):
    start: time
    end: time
    weekdays: list[Weekday] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must not repeat")
        return self


# (start, end) clock times, for example ("08:00", "12:00").
TimeRange = tuple[time, time]


class PolicyConfig(ConfigModel):
    """config/policy.yaml. Field meanings are in data_model.md -> PolicyConfig."""

    policy_id: str = Field(min_length=1, max_length=100)
    status: str = Field(max_length=300)  # says whether values are ASSUMPTION or DOCUMENTED
    term_windows: list[DateWindow] = Field(min_length=1)  # A-06
    blackout_dates: list[date] = Field(default_factory=list)  # A-06
    notice_days: int = Field(ge=0)  # A-05
    duration_minutes: dict[DegreeLevel, Annotated[int, Field(gt=0)]]  # A-07
    buffer_minutes: int = Field(ge=0)
    working_hours: WorkingHours  # A-19
    required_roles: dict[DegreeLevel, list[Role]]  # A-04
    # At most 7: the planner aliases are M1..M7 (A-02, ADR-013).
    min_committee_size: dict[DegreeLevel, Annotated[int, Field(ge=1, le=7)]]  # A-02
    remote_allowed_roles: list[Role]  # A-10
    max_remote_members: int = Field(ge=0)  # A-10
    substitute_requires_approval_by: list[SubstituteApprover] = Field(min_length=1)  # A-11
    part_of_day: dict[PartOfDay, TimeRange | None]  # A-20; None = outside working hours

    @model_validator(mode="after")
    def _complete(self) -> Self:
        # Every degree level needs its own rules; a missing one would crash later.
        for field_name in ("duration_minutes", "required_roles", "min_committee_size"):
            missing = [
                level.value for level in DegreeLevel if level not in getattr(self, field_name)
            ]
            if missing:
                missing_text = ", ".join(missing)
                raise ValueError(
                    f"{field_name} needs a value for every degree level; missing: {missing_text}"
                )
        missing_parts = [part.value for part in PartOfDay if part not in self.part_of_day]
        if missing_parts:
            raise ValueError(
                f"part_of_day is missing: {', '.join(missing_parts)} (use null to disable)"
            )
        for part, time_range in self.part_of_day.items():
            if time_range is not None and time_range[1] <= time_range[0]:
                raise ValueError(f"part_of_day {part.value}: end must be after start")
        return self


class ReminderConfig(ConfigModel):
    """config/reminders.yaml: the fixed reminder cadence and message limits (AP-02, AP-03)."""

    status: str = Field(max_length=300)
    first_reminder_after_days: int = Field(ge=1)
    next_reminder_after_days: int = Field(ge=1)
    max_reminders: int = Field(ge=0)  # after the last one: NON_RESPONSIVE
    confirmation_reminder_after_days: int = Field(ge=1)  # in CONFIRMING
    clarification_min_gap_days: int = Field(ge=1)  # at most 1 clarification per this many days
    max_messages_per_member: int = Field(ge=1)  # per defense


class ModelCallConfig(ConfigModel):
    """Settings for one kind of LLM call. Used by the LLM client (ST-06)."""

    model: str = Field(min_length=1, max_length=100)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    temperature: float = Field(ge=0)
    price_in_usd_per_million_tokens: float = Field(ge=0)
    price_out_usd_per_million_tokens: float = Field(ge=0)


class ModelCalls(ConfigModel):
    extractor: ModelCallConfig
    planner: ModelCallConfig


class ModelsConfig(ConfigModel):
    """config/models.yaml. Provider and prices are not decided yet (ADR-008)."""

    status: str = Field(max_length=300)
    provider: str = Field(min_length=1, max_length=100)
    calls: ModelCalls


class AppConfig(ConfigModel):
    """Everything loaded from config/, plus the policy version hash."""

    policy: PolicyConfig
    policy_version: Sha256Hex
    reminders: ReminderConfig
    models: ModelsConfig


# ---------------------------------------------------------------- YAML reading


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """yaml.SafeLoader that also refuses duplicate keys.

    SafeLoader never builds Python objects from tags such as
    !!python/object/apply, so a config file cannot run code.
    Plain YAML keeps the *last* value of a repeated key without a warning;
    for a policy file that could silently change a rule, so we refuse it.
    """


def _mapping_without_duplicates(
    loader: _NoDuplicateKeysLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            # For example a list used as a key. Skip it here: construct_mapping
            # below raises a proper YAML error for it ("found unhashable key").
            continue
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key '{key}'", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


# Only this subclass is changed; yaml.SafeLoader itself stays as it is.
_NoDuplicateKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates
)


def read_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file safely and return its top-level mapping."""
    name = path.name
    if not path.is_file():
        raise ConfigError(f"{name}: file not found at '{path}'")
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.load(text, Loader=_NoDuplicateKeysLoader)  # a SafeLoader subclass
    except UnicodeDecodeError as error:
        raise ConfigError(f"{name}: the file is not valid UTF-8 text") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"{name}: invalid YAML: {_describe_yaml_error(error)}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{name}: the file must contain a mapping (key: value lines) at the top")
    return data


def _describe_yaml_error(error: yaml.YAMLError) -> str:
    problem = getattr(error, "problem", None) or str(error)
    mark = getattr(error, "problem_mark", None)
    if mark is not None:
        return f"{problem} (line {mark.line + 1}, column {mark.column + 1})"
    return problem


# [ModelT: ConfigModel] is Python 3.12 generic syntax: "_validate returns the same
# class it was given", so load_policy returns a PolicyConfig, not just a ConfigModel.
def _validate[ModelT: ConfigModel](
    model_class: type[ModelT], data: dict[str, Any], name: str
) -> ModelT:
    try:
        return model_class.model_validate(data)
    except ValidationError as error:
        raise ConfigError(_format_validation_error(name, error)) from None


def _format_validation_error(name: str, error: ValidationError) -> str:
    """One line per problem: 'working_hours.end: missing (this field is required)'."""
    lines = [f"{name} is invalid ({error.error_count()} problem(s)):"]
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(whole file)"
        if item["type"] == "missing":
            description = "missing (this field is required)"
        elif item["type"] == "extra_forbidden":
            description = "unknown field, not allowed (check the spelling)"
        else:
            description = item["msg"]
        lines.append(f"  - {location}: {description}")
    return "\n".join(lines)


# ---------------------------------------------------------------- public loaders


def load_policy(path: Path) -> PolicyConfig:
    return _validate(PolicyConfig, read_yaml(path), path.name)


def load_reminders(path: Path) -> ReminderConfig:
    return _validate(ReminderConfig, read_yaml(path), path.name)


def load_models(path: Path) -> ModelsConfig:
    return _validate(ModelsConfig, read_yaml(path), path.name)


def policy_version(policy: PolicyConfig) -> str:
    """SHA-256 of the policy *values* (canonical JSON), not of the file bytes.

    So comments, key order, spaces, and CRLF vs LF line endings do not change
    the version, but any changed value does (data_model.md -> Defense.policy_version).
    """
    return sha256_hex(canonical_json(policy.model_dump(mode="json")))


def load_app_config(settings: Settings | None = None) -> AppConfig:
    """Load and check every file in the config directory."""
    if settings is None:
        settings = Settings()
    config_dir = settings.config_dir
    policy = load_policy(config_dir / "policy.yaml")
    return AppConfig(
        policy=policy,
        policy_version=policy_version(policy),
        reminders=load_reminders(config_dir / "reminders.yaml"),
        models=load_models(config_dir / "models.yaml"),
    )
