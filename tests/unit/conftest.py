"""Shared test data for the unit tests.

`VALID_EXAMPLES` holds one small, valid set of field values for every model
class. Tests use it to (1) prove each model accepts good data and (2) change
one field at a time to prove bad data is rejected.

All names and addresses are fake (synthetic data only, R3 rule 9).
"""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, settings

# Hypothesis (property tests, ST-03): the same examples on every run and every
# machine (derandomize), no example database written to disk, and no time limit
# per example (Windows CI runners are slower). Rule 6: reproducibility.
settings.register_profile(
    "project",
    derandomize=True,
    database=None,
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("project")

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

T0 = "2026-11-02T08:00:00Z"
T1 = "2026-11-02T08:05:00Z"
HEX_A = "a" * 64
HEX_B = "b" * 64


def _yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _examples() -> dict[str, dict[str, Any]]:
    """Class name -> keyword arguments that make a valid instance."""
    slot = {"start": "2026-11-17T08:00:00Z", "end": "2026-11-17T09:30:00Z"}
    return {
        # ---------------------------------------------------------- app.core.models
        "Slot": slot,
        "Defense": {
            "id": "d-1",
            "owner_user_id": "u-1",
            "title": "Robust GPS Receivers on Small FPGAs",
            "degree_level": "MSC",
            "window_start": "2026-11-16",
            "window_end": "2026-11-27",
            "attendance_mode": "HYBRID_ALLOWED",
            "expected_audience": 20,
            "status": "DRAFT",
            "state_version": 0,
            "policy_version": HEX_A,
            "scheduled_slot": None,
            "agent_paused": False,
            "previous_status": None,
            "budget_spent_usd": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "created_at": T0,
            "updated_at": T0,
        },
        "CommitteeMember": {
            "id": "m-1",
            "defense_id": "d-1",
            "alias": "M1",
            "full_name": "Dana Example",
            "email": "dana.example@example.edu",
            "role": "ADVISOR",
            "is_mandatory": True,
            "timezone": "Asia/Beirut",
            "attendance": "IN_PERSON",
            "calendar_opt_in": False,
            "status": "NOT_CONTACTED",
            "messages_sent": 0,
            "reminders_sent": 0,
            "clarifications_sent": 0,
            "last_contacted_at": None,
            "last_replied_at": None,
            "recheck_at": None,
        },
        "AvailabilityStatement": {
            "id": "s-1",
            "member_id": "m-1",
            "source_message_id": "msg-1",
            "source": "EMAIL",
            "kind": "AVAILABLE",
            "raw_expression": '{"day":"TUE","part":"AFTERNOON"}',
            "intervals_utc": [["2026-11-17T11:00:00Z", "2026-11-17T15:00:00Z"]],
            "condition": None,
            "private_reason": None,
            "confidence": 0.9,
            "issues": [],
            "status": "ACTIVE",
            "supersedes_id": None,
            "observed_at": T0,
            "extractor_version": "extractor-v1",
        },
        "Room": {
            "id": "r-1",
            "name": "B-204",
            "building": "Building B",
            "capacity": 30,
            "hybrid_capable": True,
        },
        "Booking": {
            "id": "b-1",
            "defense_id": "d-1",
            "room_id": "r-1",
            "slot_start_utc": slot["start"],
            "slot_end_utc": slot["end"],
            "status": "REQUESTED",
            "external_ref": None,
            "idempotency_key": "d-1:a-1:book",
        },
        "Message": {
            "id": "msg-1",
            "defense_id": "d-1",
            "member_id": "m-1",
            "direction": "IN",
            "provider_message_id": "prov-1",
            "content_hash": HEX_B,
            "thread_token": "[DEF-7Q2K]",
            "from_addr": "dana.example@example.edu",
            "to_addrs": ["coordination@example.edu"],
            "subject": "Re: Defense availability [DEF-7Q2K]",
            "body_raw": "Tuesday afternoon works for me.",
            "body_redacted": "Tuesday afternoon works for me.",
            "sender_verified": True,
            "processing_status": "NEW",
            "purpose": None,
            "structured_meta": None,
            "template_id": None,
            "created_by": "system",
        },
        "ApprovalRequest": {
            "id": "a-1",
            "defense_id": "d-1",
            "action_type": "SCHEDULE",
            "payload": {"slot_id": "slot-1", "room_id": "r-1"},
            "payload_hash": HEX_A,
            "state_version": 3,
            "risk_tier": "R2",
            "agent_rationale": "All mandatory members are available; earliest slot.",
            "validator_report": {"notice": "ok"},
            "status": "PENDING",
            "decided_by": None,
            "decided_at": None,
            "decision_note": None,
            "expires_at": "2026-11-04T08:00:00Z",
        },
        "Timer": {
            "id": "t-1",
            "defense_id": "d-1",
            "member_id": "m-1",
            "kind": "REMINDER",
            "fire_at": "2026-11-05T08:00:00Z",
            "status": "PENDING",
        },
        "WorkflowEvent": {
            "seq": 1,
            "defense_id": "d-1",
            "type": "STATUS_CHANGED",
            "actor": "system",
            "payload_redacted": {"from": "DRAFT", "to": "COLLECTING"},
            "sim_time": T0,
            "wall_time": T1,
            "causation_id": None,
            "prev_hash": "0" * 64,
            "hash": HEX_A,
        },
        "TraceSpan": {
            "run_id": "run-1",
            "span_id": "span-1",
            "parent_id": None,
            "kind": "TOOL",
            "name": "find_candidate_slots",
            "start": T0,
            "end": T1,
            "latency_ms": 12.5,
            "model": None,
            "prompt_version": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "retries": 0,
            "outcome": "OK",
            "error_code": None,
            "attributes_redacted": {},
        },
        "User": {
            "id": "u-1",
            "display_name": "Student One",
            "role": "STUDENT",
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$fakesalt$fakehash",
            "api_token_hash": None,
        },
        # ---------------------------------------------------------- app.core.config
        "DateWindow": {"start": "2026-09-01", "end": "2026-12-20"},
        "WorkingHours": {
            "start": "08:00",
            "end": "18:00",
            "weekdays": ["MON", "TUE", "WED", "THU", "FRI"],
        },
        "PolicyConfig": _yaml("policy.yaml"),
        "ReminderConfig": _yaml("reminders.yaml"),
        "ModelCallConfig": _yaml("models.yaml")["calls"]["extractor"],
        "ModelCalls": _yaml("models.yaml")["calls"],
        "ModelsConfig": _yaml("models.yaml"),
        "SolverConfig": _yaml("solver.yaml"),
        "Settings": {"_env_file": None, "app_env": "test"},
        "AppConfig": {
            "policy": _yaml("policy.yaml"),
            "policy_version": HEX_A,
            "reminders": _yaml("reminders.yaml"),
            "models": _yaml("models.yaml"),
            "solver": _yaml("solver.yaml"),
        },
    }


VALID_EXAMPLES = _examples()


@pytest.fixture
def example() -> Any:
    """Return a fresh copy of the example for a class name (safe to modify)."""

    def _get(name: str) -> dict[str, Any]:
        return copy.deepcopy(VALID_EXAMPLES[name])

    return _get
