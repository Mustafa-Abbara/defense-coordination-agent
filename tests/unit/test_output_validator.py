"""OutputValidator: blocks leaks and bad dates in agent-written text (ST-03, FM-21, TH-02).

The recipient is M2. M1 and M3 are "other members". Window 16-27 Nov 2026.
All names, emails, reasons and canaries are synthetic.
"""

from datetime import date
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.enums import OutputProblemCode
from app.services.output_validator import (
    OutputCheck,
    OutputContext,
    ProtectedMember,
    check_outbound_text,
    normalize,
)

MEMBERS = [
    ProtectedMember(alias="M1", full_name="Dana Example", email="dana.e@uni.edu"),
    ProtectedMember(alias="M2", full_name="Rami Sample", email="rami.s@uni.edu"),
    ProtectedMember(alias="M3", full_name="Lea Testperson", email="lea.t@uni.edu"),
]
SECRET_REASON = "dentist CANARY-7F3A"


def context(**changes: Any) -> OutputContext:
    values: dict[str, Any] = {
        "recipient_alias": "M2",
        "members": MEMBERS,
        "private_reasons": [SECRET_REASON, "teaching a course"],
        "window_start": date(2026, 11, 16),
        "window_end": date(2026, 11, 27),
        "max_length": 400,
    }
    values.update(changes)
    return OutputContext.model_validate(values)


def check(text: str, **changes: Any) -> OutputCheck:
    return check_outbound_text(text, context(**changes))


def codes(result: OutputCheck) -> list[str]:
    return sorted(problem.code.value for problem in result.problems)


GOOD = "Could you confirm whether Tuesday 17 November 2026, 10:00-11:30, works for you?"


# ---------------------------------------------------------------- clean text


def test_a_normal_clarification_passes() -> None:
    result = check(GOOD)
    assert result.ok
    assert result.problems == []


def test_recipient_may_be_named_and_aliased() -> None:
    assert check("Dear Rami Sample (M2), is Wed 18 Nov fine?").ok


@pytest.mark.parametrize(
    "text",
    [
        "Is 2026-11-24 in the afternoon possible?",
        "Would Nov 20 or Fri 27 Nov suit you?",
        "Thursday, November 19th works for the others.",
        "You may answer by Friday. The defense lasts 90 minutes.",  # 'may' is not a date
        "Please reply at 10.30 or 14:00.",  # times, not dates
    ],
)
def test_ordinary_wording_is_not_blocked(text: str) -> None:
    assert check(text).ok, check(text).problems


# ---------------------------------------------------------------- privacy (FM-21, TH-02)


def test_other_member_alias_is_blocked() -> None:
    result = check("M3 cannot make Tuesday. Can you?")
    assert codes(result) == ["OTHER_MEMBER_ALIAS"]
    assert "M3" in result.problems[0].detail  # aliases are safe to name


@pytest.mark.parametrize(
    "text",
    [
        "Dana Example is busy then.",
        "Prof. EXAMPLE suggested Tuesday.",  # surname alone, other case
        "Dana​ Example is busy then.",  # zero-width space hidden inside
        "Ｄａｎａ Ｅｘａｍｐｌｅ is busy then.",  # full-width letters
        "Lea Testperson\nwill join.",  # newline instead of a space
    ],
)
def test_other_member_name_is_blocked_even_when_disguised(text: str) -> None:
    result = check(text)
    assert codes(result) == ["PROTECTED_TERM"]
    # The error never repeats the name (the planner must not learn it).
    detail = result.problems[0].detail.casefold()
    assert "dana" not in detail and "example" not in detail and "testperson" not in detail


def test_private_reason_and_canary_are_blocked() -> None:
    assert codes(check("They have a dentist CANARY-7F3A appointment.")) == ["PROTECTED_TERM"]
    assert codes(check("Someone is teaching a course then.")) == ["PROTECTED_TERM"]
    assert codes(check("Token canary-9z9z found.")) == ["PROTECTED_TERM"]


def test_any_email_and_any_link_are_blocked() -> None:
    assert codes(check("Write to rami.s@uni.edu please.")) == ["EMAIL_ADDRESS"]
    assert "URL" in codes(check("See https://calendar.invalid/slots"))
    assert "URL" in codes(check("See www.slots.net"))
    assert codes(check("Book at evil.test/x now")) == ["URL"]
    assert codes(check("Visit doodle.com today")) == ["URL"]


def test_owner_summary_may_mention_aliases_and_reasons_but_not_links() -> None:
    owner = {"recipient_alias": None, "max_length": 600}
    assert check("M3 is teaching a course on Tuesdays; CANARY-7F3A noted.", **owner).ok
    assert codes(check("M3 sent http://phish.invalid", **owner)) == ["URL"]
    assert codes(check("Dana Example is late.", **owner)) == ["PROTECTED_TERM"]


# ---------------------------------------------------------------- dates (FM-15)


def test_ambiguous_numeric_date_is_blocked() -> None:
    assert codes(check("Does 3/11 work?")) == ["AMBIGUOUS_NUMERIC_DATE"]
    assert codes(check("Does 03.11.2026 work?")) == ["AMBIGUOUS_NUMERIC_DATE"]


def test_impossible_date_is_blocked() -> None:
    assert codes(check("Is 31 Nov possible?")) == ["INVALID_DATE"]
    assert codes(check("Is 2026-13-02 possible?")) == ["INVALID_DATE"]


def test_date_outside_window_is_blocked() -> None:
    result = check("Could we do Thursday 3 December 2026?")
    assert codes(result) == ["DATE_OUTSIDE_WINDOW"]
    assert check("How about 1 Dec?").ok is False


def test_weekday_must_match_the_date() -> None:
    # 18 Nov 2026 is a Wednesday.
    result = check("Is Tuesday 18 November ok?")
    assert codes(result) == ["WEEKDAY_DATE_MISMATCH"]
    assert "Wednesday" in result.problems[0].detail
    assert check("Is Wednesday 18 November ok?").ok


def test_year_is_taken_from_the_window_across_new_year() -> None:
    winter = {"window_start": date(2026, 12, 28), "window_end": date(2027, 1, 8)}
    assert check("Is Mon 4 Jan ok?", **winter).ok  # 4 Jan 2027 is a Monday
    assert codes(check("Is Mon 5 Jan ok?", **winter)) == ["WEEKDAY_DATE_MISMATCH"]


# ---------------------------------------------------------------- length and shape


def test_too_long_and_empty() -> None:
    assert codes(check("a" * 401)) == ["TOO_LONG"]
    assert check("a" * 400).ok
    assert codes(check("   \n ")) == ["EMPTY"]


def test_several_problems_are_all_reported() -> None:
    # The email also contains M1's first name, so PROTECTED_TERM fires too.
    text = "M1 (dana.e@uni.edu) said 3/11 at https://x.invalid is fine."
    assert codes(check(text)) == [
        "AMBIGUOUS_NUMERIC_DATE",
        "EMAIL_ADDRESS",
        "OTHER_MEMBER_ALIAS",
        "PROTECTED_TERM",
        "URL",
    ]


def test_context_rejects_bad_settings() -> None:
    with pytest.raises(ValidationError):
        context(max_length=0)
    with pytest.raises(ValidationError):
        context(window_start=date(2026, 11, 27), window_end=date(2026, 11, 16))
    with pytest.raises(ValidationError):
        context(recipient_alias="M9")


def test_private_fields_are_hidden_in_repr() -> None:
    shown = repr(context())
    assert "dana.e@" not in shown and "CANARY" not in shown and "Dana" not in shown


def test_normalize_removes_invisible_characters() -> None:
    assert normalize("A​B⁠C  \t D") == "abc d"


# ---------------------------------------------------------------- property


@given(
    prefix=st.text(alphabet=st.characters(categories=["L", "N", "Zs", "P"]), max_size=60),
    suffix=st.text(alphabet=st.characters(categories=["L", "N", "Zs", "P"]), max_size=60),
    secret=st.sampled_from(["Dana Example", "dana.e@uni.edu", SECRET_REASON, "M1"]),
)
def test_a_planted_secret_is_always_blocked(prefix: str, suffix: str, secret: str) -> None:
    # Whatever text surrounds it (separated by spaces), another member's name,
    # email, private reason, or alias never passes.
    result = check(f"{prefix} {secret} {suffix}")
    assert not result.ok
    assert set(codes(result)) & {"PROTECTED_TERM", "EMAIL_ADDRESS", "OTHER_MEMBER_ALIAS"}
    for problem in result.problems:
        assert problem.code is not OutputProblemCode.EMPTY
