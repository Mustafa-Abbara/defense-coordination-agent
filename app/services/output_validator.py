"""OutputValidator: checks every outbound text the agent wrote (ST-03, FM-21, TH-02).

The planner writes short texts: a clarification question (T04) or an escalation
summary (T10). Before such a text is used, this module looks for:

- another member's alias (M1..M7), name, or a private reason, and canary strings
  (the synthetic secrets planted in private reasons for leak tests, SEC-02);
- any email address and any link (R3 rule 8: no links in agent-written text);
- dates that are ambiguous ("3/11"), impossible ("31 Nov"), outside the defense
  window, or whose weekday is wrong ("Tuesday 18 Nov 2026" is a Wednesday);
- a text that is empty or too long.

Before matching, the text is normalized (NFKC) and invisible "format" characters
such as zero-width spaces are removed, so "Da<zero-width space>na" or full-width
letters cannot hide a name from the check.

Problem details never repeat a name, an email, or a reason. They are returned to
the planner so it can rewrite once (interfaces.md T04), and the planner must not
learn the protected value from the error message.
"""

import re
import unicodedata
from datetime import date
from typing import Self

from pydantic import EmailStr, Field, model_validator

from app.core.enums import OutputProblemCode
from app.core.fields import MemberAlias, StrictModel


class ProtectedMember(StrictModel):
    """One committee member as the validator needs it."""

    alias: MemberAlias
    full_name: str = Field(min_length=1, max_length=120, repr=False)  # PII
    email: EmailStr = Field(repr=False)  # PII


class OutputContext(StrictModel):
    """What a text may and may not contain."""

    # The member who will receive the text, or None when it goes to the owner student.
    recipient_alias: MemberAlias | None
    members: list[ProtectedMember] = Field(max_length=7)
    private_reasons: list[str] = Field(default_factory=list, repr=False)  # Restricted
    window_start: date
    window_end: date
    max_length: int = Field(ge=1, le=4000)

    @model_validator(mode="after")
    def _window_in_order(self) -> Self:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        return self

    @property
    def for_owner(self) -> bool:
        # Escalation summaries go only to the owner student, who may see aliases and
        # private reasons (interfaces.md T10). Everything else is still checked.
        return self.recipient_alias is None


class OutputProblem(StrictModel):
    code: OutputProblemCode
    detail: str = Field(max_length=200)  # safe to show: never the protected value itself


class OutputCheck(StrictModel):
    ok: bool
    problems: list[OutputProblem]


# ---------------------------------------------------------------- patterns

_ALIAS = re.compile(r"(?<![a-z0-9])m([1-7])(?![a-z0-9])")
_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_URL = re.compile(
    r"https?://|www\."
    r"|(?<![a-z0-9@.-])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|edu|gov|io|info|biz|co|me|ly|app|dev|xyz|example)(?![a-z0-9])"
    r"|(?<![a-z0-9@.-])[a-z0-9-]+\.[a-z]{2,}/"
)
_CANARY = re.compile(r"canary-[a-z0-9]+")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-z])"
)
_WEEKDAY = (
    r"(?:(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?"
    r"|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\.?,?\s+)?"
)
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"
# "Tue 17 Nov 2026", "17th November"
_DAY_MONTH = re.compile(r"(?<![a-z0-9])" + _WEEKDAY + _DAY + r"\s+" + _MONTH + _YEAR)
# "Tuesday, November 17, 2026", "Nov 17"
_MONTH_DAY = re.compile(r"(?<![a-z0-9])" + _WEEKDAY + _MONTH + r"\s+" + _DAY + r"(?![0-9])" + _YEAR)
# "2026-11-17", optionally after a weekday
_ISO = re.compile(r"(?<![a-z0-9])" + _WEEKDAY + r"(\d{4})-(\d{2})-(\d{2})(?![0-9])")
# "3/11", "3/11/2026", "03.11.2026": day/month order is unclear (FM-15)
_NUMERIC = re.compile(
    r"(?<![0-9/.])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![0-9/])|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"
)

_WEEKDAY_NUMBERS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Name parts shorter than this are not checked alone ("Li", "Al"), to avoid
# blocking ordinary words; the full name is always checked.
_MIN_NAME_PART = 4
_MIN_REASON_LENGTH = 4


# ---------------------------------------------------------------- main function


def check_outbound_text(text: str, context: OutputContext) -> OutputCheck:
    """Check one outbound text. ok=False means it must not be sent."""
    problems: list[OutputProblem] = []
    if not text.strip():
        problems.append(_problem(OutputProblemCode.EMPTY, "the text is empty"))
    if len(text) > context.max_length:
        problems.append(
            _problem(
                OutputProblemCode.TOO_LONG, f"the text is longer than {context.max_length} chars"
            )
        )

    clean = normalize(text)
    problems += _alias_problems(clean, context)
    problems += _protected_term_problems(clean, context)
    if _EMAIL.search(clean):
        problems.append(_problem(OutputProblemCode.EMAIL_ADDRESS, "contains an email address"))
    if _URL.search(clean):
        problems.append(_problem(OutputProblemCode.URL, "contains a link or web address"))
    problems += _date_problems(clean, context)

    unique: list[OutputProblem] = []
    for problem in problems:
        if problem not in unique:
            unique.append(problem)
    return OutputCheck(ok=not unique, problems=unique)


def normalize(text: str) -> str:
    """Lower-case text with look-alike characters unified and invisible ones removed."""
    text = unicodedata.normalize("NFKC", text)
    # Category "Cf" = invisible format characters (zero-width space, joiners, ...).
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.casefold()
    return " ".join(text.split())  # all runs of spaces/newlines -> one space


# ---------------------------------------------------------------- privacy checks


def _alias_problems(clean: str, context: OutputContext) -> list[OutputProblem]:
    if context.for_owner:
        return []
    found = []
    for match in _ALIAS.finditer(clean):
        alias = f"M{match.group(1)}"
        if alias != context.recipient_alias:
            # Aliases are pseudonyms the planner already knows, so naming one is safe.
            found.append(
                _problem(OutputProblemCode.OTHER_MEMBER_ALIAS, f"mentions another member ({alias})")
            )
    return found


def _protected_term_problems(clean: str, context: OutputContext) -> list[OutputProblem]:
    terms: list[str] = []
    for member in context.members:
        if member.alias == context.recipient_alias:
            continue  # the recipient's own name is not a leak
        name = normalize(member.full_name)
        terms.append(name)
        terms += [part for part in re.split(r"[\s.'-]+", name) if len(part) >= _MIN_NAME_PART]
    if not context.for_owner:
        terms += [normalize(r) for r in context.private_reasons if len(r) >= _MIN_REASON_LENGTH]
        if _CANARY.search(clean):
            return [_problem(OutputProblemCode.PROTECTED_TERM, "contains a protected term")]

    for term in terms:
        if term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", clean):
            # Deliberately vague: the planner must not learn the value from the error.
            return [_problem(OutputProblemCode.PROTECTED_TERM, "contains a protected term")]
    return []


# ---------------------------------------------------------------- date checks


def _date_problems(clean: str, context: OutputContext) -> list[OutputProblem]:
    problems: list[OutputProblem] = []
    if _NUMERIC.search(clean):
        problems.append(
            _problem(
                OutputProblemCode.AMBIGUOUS_NUMERIC_DATE,
                "write dates with a month name or as YYYY-MM-DD, not like 3/11",
            )
        )
    for weekday, year, month, day in _mentioned_dates(clean):
        written = f"{day} {_month_label(month)}"
        if year is None:
            year = _year_for(month, day, context)
        try:
            found = date(year, month, day)
        except ValueError:
            problems.append(_problem(OutputProblemCode.INVALID_DATE, f"{written} does not exist"))
            continue
        label = found.strftime("%d %b %Y")
        if not context.window_start <= found <= context.window_end:
            problems.append(
                _problem(OutputProblemCode.DATE_OUTSIDE_WINDOW, f"{label} is outside the window")
            )
        if weekday is not None and found.weekday() != _WEEKDAY_NUMBERS[weekday[:3]]:
            problems.append(
                _problem(
                    OutputProblemCode.WEEKDAY_DATE_MISMATCH,
                    f"{label} is a {_WEEKDAY_NAMES[found.weekday()]}",
                )
            )
    return problems


def _mentioned_dates(clean: str) -> list[tuple[str | None, int | None, int, int]]:
    """(weekday text or None, year or None, month, day) for every date in the text."""
    found: list[tuple[str | None, int | None, int, int]] = []
    for m in _DAY_MONTH.finditer(clean):
        found.append(
            (m.group(1), _int_or_none(m.group(4)), _MONTHS[m.group(3)[:3]], int(m.group(2)))
        )
    for m in _MONTH_DAY.finditer(clean):
        found.append(
            (m.group(1), _int_or_none(m.group(4)), _MONTHS[m.group(2)[:3]], int(m.group(3)))
        )
    for m in _ISO.finditer(clean):
        found.append((m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))))
    return found


def _year_for(month: int, day: int, context: OutputContext) -> int:
    """A date written without a year: take the window year that puts it inside the window."""
    for year in sorted({context.window_start.year, context.window_end.year}):
        try:
            if context.window_start <= date(year, month, day) <= context.window_end:
                return year
        except ValueError:
            continue
    return context.window_start.year


def _month_label(month: int) -> str:
    return list(_MONTHS)[month - 1].capitalize() if 1 <= month <= 12 else f"month {month}"


def _int_or_none(text: str | None) -> int | None:
    return int(text) if text is not None else None


def _problem(code: OutputProblemCode, detail: str) -> OutputProblem:
    return OutputProblem(code=code, detail=detail)
