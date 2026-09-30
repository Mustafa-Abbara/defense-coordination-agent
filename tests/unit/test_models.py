"""Domain models reject bad data (ST-02).

Every entity in docs/data_model.md is a Pydantic model. These tests check
behavior, not implementation: good data is accepted, and each kind of bad
data (unknown field, naive time, fake time zone, wrong enum, ...) is refused.
"""

import inspect
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from conftest import VALID_EXAMPLES
from pydantic import BaseModel, ValidationError

from app.core import config, models
from app.core.enums import IssueCode, StatementKind
from app.core.fields import StrictModel

REPO_ROOT = Path(__file__).resolve().parents[2]

Example = Callable[[str], dict[str, Any]]


def model_classes() -> list[type[BaseModel]]:
    """Every Pydantic model class defined in the two ST-02 modules."""
    found = []
    for module in (models, config):
        for _, obj in inspect.getmembers(module, inspect.isclass):
            defined_here = obj.__module__ == module.__name__
            # Base classes without fields (ConfigModel) are building blocks, not models.
            if issubclass(obj, BaseModel) and defined_here and obj.model_fields:
                found.append(obj)
    return found


MODEL_CLASSES = model_classes()
MODEL_IDS = [cls.__name__ for cls in MODEL_CLASSES]


def error_types(error: ValidationError) -> set[str]:
    return {item["type"] for item in error.errors()}


# ---------------------------------------------------------------- extra="forbid" (acceptance #4)


def test_the_two_modules_define_all_expected_entities() -> None:
    # One model per entity in data_model.md (plus Slot), and the config schemas.
    expected = {
        "Defense",
        "CommitteeMember",
        "AvailabilityStatement",
        "Room",
        "Booking",
        "Message",
        "ApprovalRequest",
        "Timer",
        "WorkflowEvent",
        "TraceSpan",
        "User",
        "Slot",
        "PolicyConfig",
    }
    assert expected <= set(MODEL_IDS)


def test_every_model_has_a_valid_example() -> None:
    # A new model without an example would silently skip the checks below.
    assert set(MODEL_IDS) == set(VALID_EXAMPLES)


@pytest.mark.parametrize("cls", MODEL_CLASSES, ids=MODEL_IDS)
def test_every_model_forbids_extra_fields(cls: type[BaseModel]) -> None:
    assert cls.model_config.get("extra") == "forbid"


def test_base_classes_forbid_extra_fields_too() -> None:
    assert StrictModel.model_config.get("extra") == "forbid"
    assert config.ConfigModel.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("cls", MODEL_CLASSES, ids=MODEL_IDS)
def test_valid_example_is_accepted(cls: type[BaseModel], example: Example) -> None:
    cls(**example(cls.__name__))


@pytest.mark.parametrize("cls", MODEL_CLASSES, ids=MODEL_IDS)
def test_unknown_field_is_rejected(cls: type[BaseModel], example: Example) -> None:
    # Hostile input: an injected field such as "approved": true in LLM output.
    data = example(cls.__name__)
    data["is_admin"] = True
    with pytest.raises(ValidationError) as caught:
        cls(**data)
    assert "extra_forbidden" in error_types(caught.value)


# ---------------------------------------------------------------- time (data_model.md: UTC)


def test_naive_datetime_is_rejected(example: Example) -> None:
    data = example("Timer")
    data["fire_at"] = datetime(2026, 11, 5, 8, 0)  # noqa: DTZ001  (naive on purpose)
    with pytest.raises(ValidationError) as caught:
        models.Timer(**data)
    assert "timezone_aware" in error_types(caught.value)


def test_naive_datetime_string_is_rejected(example: Example) -> None:
    data = example("Timer")
    data["fire_at"] = "2026-11-05T08:00:00"
    with pytest.raises(ValidationError):
        models.Timer(**data)


def test_other_offset_is_converted_to_utc(example: Example) -> None:
    data = example("Timer")
    beirut_winter = timezone(timedelta(hours=2))
    data["fire_at"] = datetime(2026, 11, 5, 10, 0, tzinfo=beirut_winter)
    timer = models.Timer(**data)
    assert timer.fire_at == datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
    assert timer.fire_at.utcoffset() == timedelta(0)


def test_assignment_is_validated_too(example: Example) -> None:
    timer = models.Timer(**example("Timer"))
    with pytest.raises(ValidationError):
        timer.fire_at = datetime(2026, 11, 5, 8, 0)  # noqa: DTZ001


def test_slot_end_must_be_after_start(example: Example) -> None:
    data = example("Slot")
    data["end"] = data["start"]
    with pytest.raises(ValidationError, match="end must be after start"):
        models.Slot(**data)


def test_booking_end_must_be_after_start(example: Example) -> None:
    data = example("Booking")
    data["slot_end_utc"] = "2026-11-17T07:00:00Z"
    with pytest.raises(ValidationError):
        models.Booking(**data)


def test_defense_window_end_cannot_be_before_start(example: Example) -> None:
    data = example("Defense")
    data["window_end"] = "2026-11-01"
    with pytest.raises(ValidationError, match="window_end"):
        models.Defense(**data)


def test_statement_intervals_must_be_ordered(example: Example) -> None:
    data = example("AvailabilityStatement")
    data["intervals_utc"] = [["2026-11-17T15:00:00Z", "2026-11-17T11:00:00Z"]]
    with pytest.raises(ValidationError, match="end must be after start"):
        models.AvailabilityStatement(**data)


def test_span_cannot_end_before_it_starts(example: Example) -> None:
    data = example("TraceSpan")
    data["end"] = "2026-11-02T07:00:00Z"
    with pytest.raises(ValidationError):
        models.TraceSpan(**data)


# ---------------------------------------------------------------- time zones, aliases, emails


@pytest.mark.parametrize("zone", ["Asia/Beirut", "Europe/Paris", "America/New_York", "UTC"])
def test_real_iana_time_zones_are_accepted(zone: str, example: Example) -> None:
    data = example("CommitteeMember")
    data["timezone"] = zone
    assert models.CommitteeMember(**data).timezone == zone


@pytest.mark.parametrize(
    "zone",
    [
        "Mars/Olympus_Mons",
        "../../etc/passwd",
        "",
        "UTC+3",
        "Asia/Beirut; DROP TABLE",
        # Regression (found on Windows): Windows file names ignore trailing spaces
        # and case, so these were accepted there but refused on Linux.
        "CET ",
        "Asia/Beirut ",
        "asia/beirut",
        "ASIA/BEIRUT",
        "localtime",  # a machine-specific link on Linux, not an IANA name
    ],
)
def test_invalid_time_zone_is_rejected(zone: str, example: Example) -> None:
    data = example("CommitteeMember")
    data["timezone"] = zone
    with pytest.raises(ValidationError):
        models.CommitteeMember(**data)


@pytest.mark.parametrize("alias", ["M0", "M8", "m1", "M10", "M1 ", "Dana", ""])
def test_alias_must_be_m1_to_m7(alias: str, example: Example) -> None:
    data = example("CommitteeMember")
    data["alias"] = alias
    with pytest.raises(ValidationError):
        models.CommitteeMember(**data)


@pytest.mark.parametrize("email", ["not-an-email", "dana@", "@example.edu", "a b@example.edu"])
def test_malformed_email_is_rejected(email: str, example: Example) -> None:
    data = example("CommitteeMember")
    data["email"] = email
    with pytest.raises(ValidationError):
        models.CommitteeMember(**data)


# ---------------------------------------------------------------- ranges and enums


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_confidence_must_be_between_0_and_1(value: float, example: Example) -> None:
    data = example("AvailabilityStatement")
    data["confidence"] = value
    with pytest.raises(ValidationError):
        models.AvailabilityStatement(**data)


@pytest.mark.parametrize(
    ("cls_name", "field"),
    [
        ("Defense", "state_version"),
        ("Defense", "tokens_in"),
        ("Defense", "budget_spent_usd"),
        ("CommitteeMember", "messages_sent"),
        ("TraceSpan", "cost_usd"),
    ],
)
def test_counters_cannot_be_negative(cls_name: str, field: str, example: Example) -> None:
    data = example(cls_name)
    data[field] = -1
    with pytest.raises(ValidationError):
        getattr(models, cls_name)(**data)


def test_unknown_enum_value_is_rejected(example: Example) -> None:
    data = example("Defense")
    data["status"] = "HACKED"
    with pytest.raises(ValidationError):
        models.Defense(**data)


def test_status_cannot_be_assigned_an_unknown_value(example: Example) -> None:
    defense = models.Defense(**example("Defense"))
    with pytest.raises(ValidationError):
        defense.status = "APPROVED_BY_EMAIL"  # type: ignore[assignment]


def test_approval_risk_tier_is_always_r2(example: Example) -> None:
    data = example("ApprovalRequest")
    data["risk_tier"] = "R1"
    with pytest.raises(ValidationError):
        models.ApprovalRequest(**data)


def test_agent_rationale_is_capped_at_500_characters(example: Example) -> None:
    data = example("ApprovalRequest")
    data["agent_rationale"] = "x" * 501
    with pytest.raises(ValidationError):
        models.ApprovalRequest(**data)


@pytest.mark.parametrize("field", ["policy_version"])
@pytest.mark.parametrize("value", ["abc", "G" * 64, "A" * 64])
def test_hashes_must_be_64_lowercase_hex(field: str, value: str, example: Example) -> None:
    data = example("Defense")
    data[field] = value
    with pytest.raises(ValidationError):
        models.Defense(**data)


@pytest.mark.parametrize("actor", ["user:u-1", "agent", "executor", "system", "sim"])
def test_known_event_actors_are_accepted(actor: str, example: Example) -> None:
    data = example("WorkflowEvent")
    data["actor"] = actor
    assert models.WorkflowEvent(**data).actor == actor


@pytest.mark.parametrize("actor", ["admin", "user:", "agent ", "user:u-1;rm", "planner"])
def test_unknown_event_actors_are_rejected(actor: str, example: Example) -> None:
    data = example("WorkflowEvent")
    data["actor"] = actor
    with pytest.raises(ValidationError):
        models.WorkflowEvent(**data)


# ---------------------------------------------------------------- cross-field rules


def test_email_statement_needs_its_source_message(example: Example) -> None:
    data = example("AvailabilityStatement")
    data["source_message_id"] = None
    with pytest.raises(ValidationError, match="source_message_id"):
        models.AvailabilityStatement(**data)


@pytest.mark.parametrize("source", ["MANUAL", "CALENDAR"])
def test_manual_or_calendar_statement_has_no_source_message(source: str, example: Example) -> None:
    data = example("AvailabilityStatement")
    data["source"] = source
    with pytest.raises(ValidationError, match="source_message_id"):
        models.AvailabilityStatement(**data)
    data["source_message_id"] = None
    assert models.AvailabilityStatement(**data).source == source


def test_outbound_message_needs_a_purpose(example: Example) -> None:
    data = example("Message")
    data["direction"] = "OUT"
    with pytest.raises(ValidationError, match="purpose"):
        models.Message(**data)
    data["purpose"] = "POLL"
    data["template_id"] = "poll.txt"
    assert models.Message(**data).purpose == "POLL"


def test_inbound_message_has_no_outbound_fields(example: Example) -> None:
    data = example("Message")
    data["purpose"] = "REMINDER"
    with pytest.raises(ValidationError, match="purpose"):
        models.Message(**data)


def test_quarantined_inbound_message_may_have_no_thread_token(example: Example) -> None:
    data = example("Message")
    data.update(thread_token=None, defense_id=None, member_id=None)
    data["processing_status"] = "QUARANTINED"
    assert models.Message(**data).thread_token is None


def test_a_defense_cannot_have_itself_as_previous_status(example: Example) -> None:
    data = example("Defense")
    data["status"] = "ESCALATED"
    data["previous_status"] = "ESCALATED"
    with pytest.raises(ValidationError, match="previous_status"):
        models.Defense(**data)


# ---------------------------------------------------------------- privacy (TH-07, TH-08, TH-09)

CANARY = "CANARY-7F3A"


def test_pii_fields_are_hidden_from_repr(example: Example) -> None:
    # A model printed into a log must not carry names, emails, reasons, or bodies.
    member = example("CommitteeMember")
    member.update(full_name=f"Dana {CANARY}", email="canary.7f3a@example.edu")
    statement = example("AvailabilityStatement")
    statement["private_reason"] = f"teaching {CANARY}"
    message = example("Message")
    message.update(body_raw=f"secret body {CANARY}", from_addr="canary.7f3a@example.edu")
    message["to_addrs"] = ["canary.7f3a@example.edu"]
    user = example("User")
    user["password_hash"] = f"$argon2id${CANARY}"

    texts = [
        repr(models.CommitteeMember(**member)),
        str(models.CommitteeMember(**member)),
        repr(models.AvailabilityStatement(**statement)),
        repr(models.Message(**message)),
        repr(models.User(**user)),
    ]
    for text in texts:
        assert CANARY not in text
        assert "canary.7f3a@example.edu" not in text


def test_validation_errors_do_not_repeat_the_bad_value(example: Example) -> None:
    # Errors may end up in logs; they name the field but never echo PII (TH-09).
    data = example("CommitteeMember")
    data["email"] = "canary.7f3a(at)example.edu"
    with pytest.raises(ValidationError) as caught:
        models.CommitteeMember(**data)
    assert "email" in str(caught.value)
    assert "canary.7f3a" not in str(caught.value)


def test_hidden_fields_are_still_stored(example: Example) -> None:
    # repr=False only hides the value from printing; the data is kept.
    member = models.CommitteeMember(**example("CommitteeMember"))
    assert member.email == "dana.example@example.edu"


# ---------------------------------------------------------------- consistency with docs


def _doc_codes(line_start: str) -> set[str]:
    text = (REPO_ROOT / "docs" / "data_model.md").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if row.startswith(line_start))
    return set(re.findall(r"`([A-Z_]+)`", line))


def test_issue_codes_match_data_model_doc() -> None:
    assert {code.value for code in IssueCode} == _doc_codes("| issues |")


def test_statement_kinds_match_data_model_doc() -> None:
    assert {kind.value for kind in StatementKind} == _doc_codes("| kind |")
