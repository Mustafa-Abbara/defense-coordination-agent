"""Checked building blocks shared by all models (ST-02).

Each type below is a normal Python type plus a rule. Pydantic applies the rule
every time a value is created or assigned, so no part of the code can hold,
for example, a time without a time zone.
"""

from datetime import UTC, datetime
from functools import cache
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints


class StrictModel(BaseModel):
    """Base class for every model in the project.

    - extra="forbid": an unknown field is an error, not silently dropped.
      (interfaces.md conventions; roadmap ST-02 acceptance criterion.)
    - validate_assignment=True: `defense.status = "X"` is checked too, not
      only the values given when the object is created.
    - hide_input_in_errors=True: error messages name the field and the rule
      but never repeat the bad value, which may be an email or a secret (TH-09).
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        hide_input_in_errors=True,
    )


def _to_utc(value: datetime) -> datetime:
    # AwareDatetime has already refused naive datetimes. Here we only move an
    # aware time (for example +02:00) to UTC, so all stored times compare simply.
    return value.astimezone(UTC)


# A timezone-aware datetime, always stored in UTC (data_model.md, first paragraph).
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


@cache
def _known_zone_names() -> frozenset[str]:
    # The exact list of IANA names from the time zone database (the tzdata
    # package on Windows). Read once, then kept in memory.
    # "localtime" is a link to the machine's own zone on some Linux systems; it
    # is not a real IANA name and would mean different things on different machines.
    return frozenset(available_timezones()) - {"localtime"}


def _check_iana_zone(name: str) -> str:
    # We compare with the exact list instead of just calling ZoneInfo(name).
    # Reason (bug found on Windows in ST-02): ZoneInfo opens a file named after
    # the zone, and Windows file names ignore case and trailing spaces, so
    # ZoneInfo("CET ") and ZoneInfo("asia/beirut") worked on Windows but failed
    # on Linux. An exact string match behaves the same on every machine.
    # The value itself is left out of the message on purpose.
    if name not in _known_zone_names():
        raise ValueError("not a known IANA time zone name, for example 'Asia/Beirut'")
    return name


# An IANA time zone name such as "Asia/Beirut" (needs the tzdata package on Windows).
IanaTimeZone = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(_check_iana_zone),
]

# An opaque identifier (interfaces.md: "IDs are opaque strings").
EntityId = Annotated[str, StringConstraints(min_length=1, max_length=64)]

# Planner pseudonym M1..M7 (ADR-013; at most 7 members, A-02).
MemberAlias = Annotated[str, StringConstraints(pattern=r"^M[1-7]$")]

# Lowercase SHA-256 in hex, as produced by hashlib.sha256(...).hexdigest().
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
