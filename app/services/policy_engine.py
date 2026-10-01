"""PolicyEngine: the defense rules from policy.yaml, as plain checks (ST-03).

Three questions, each with one right answer (interfaces.md -> PolicyService):

- validate_setup: is this defense set up correctly? (FR-02, before the first poll)
- check_slot:     may the defense happen in this exact slot? (solver, T07, executor)
- notice_deadline: what is the last moment the announcement can go out? (A-05)

Every rule returns a Violation instead of raising, so the setup screen can show
ALL problems at once, next to the field that causes each one (FR-02).
Messages use member aliases (M1..M7), never names or emails, so they are safe to
show to the planner and to write to logs.

Time zones: every policy rule (working hours, term, window, blackout dates,
notice) is read in the university zone `policy.timezone` (A-21).
"""

from datetime import date, datetime, timedelta

from pydantic import Field

from app.core.config import PolicyConfig, policy_version
from app.core.enums import AttendanceMode, MemberAttendance, ViolationCode
from app.core.fields import StrictModel
from app.core.models import CommitteeMember, Defense, Slot
from app.services.local_time import dates_between, local_date, wall_to_utc, weekday_of, zone

# Planner aliases are M1..M7 (ADR-013), so a committee has at most 7 members.
MAX_COMMITTEE_SIZE = 7


class DefenseSetup(StrictModel):
    """Everything the student enters on the setup screen (FR-01)."""

    defense: Defense
    members: list[CommitteeMember] = Field(max_length=20)  # size rule is a Violation, not a crash


class Violation(StrictModel):
    """One broken rule. Safe to show: no names, no emails."""

    code: ViolationCode
    field: str = Field(max_length=100)  # which setup field causes it, e.g. "window_end"
    message: str = Field(max_length=300)


class PolicyEngine:
    """Applies one loaded policy. Create it once with the policy from config."""

    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy
        self._version = policy_version(policy)

    def current(self) -> PolicyConfig:
        return self._policy

    def version(self) -> str:
        return self._version

    # ------------------------------------------------------------ setup (FR-02)

    def validate_setup(self, setup: DefenseSetup, now: datetime) -> list[Violation]:
        """Every problem with the setup. An empty list means: ready to start."""
        violations: list[Violation] = []
        violations += self._check_membership(setup)
        violations += self._check_committee(setup)
        violations += self._check_remote_members(setup)
        violations += self._check_window(setup.defense, now)
        return violations

    def _check_membership(self, setup: DefenseSetup) -> list[Violation]:
        found: list[Violation] = []
        for member in setup.members:
            if member.defense_id != setup.defense.id:
                found.append(
                    _violation(
                        ViolationCode.MEMBER_OF_OTHER_DEFENSE,
                        f"members.{member.alias}",
                        f"{member.alias} belongs to a different defense",
                    )
                )
        found += _duplicates(
            [member.alias for member in setup.members],
            setup.members,
            ViolationCode.DUPLICATE_ALIAS,
            "is used by more than one member",
        )
        # Emails are compared without case: Dana@X.edu and dana@x.edu are one person.
        found += _duplicates(
            [member.email.casefold() for member in setup.members],
            setup.members,
            ViolationCode.DUPLICATE_EMAIL,
            "has the same email as another member",
        )
        return found

    def _check_committee(self, setup: DefenseSetup) -> list[Violation]:
        degree = setup.defense.degree_level
        size = len(setup.members)
        found: list[Violation] = []
        minimum = self._policy.min_committee_size[degree]
        if size < minimum:
            found.append(
                _violation(
                    ViolationCode.COMMITTEE_TOO_SMALL,
                    "members",
                    f"a {degree.value} committee needs at least {minimum} members; it has {size}",
                )
            )
        if size > MAX_COMMITTEE_SIZE:
            found.append(
                _violation(
                    ViolationCode.COMMITTEE_TOO_LARGE,
                    "members",
                    f"at most {MAX_COMMITTEE_SIZE} members are supported; it has {size}",
                )
            )
        # Each required role needs at least one MANDATORY member with that role.
        # A second member with the same role may be optional.
        mandatory_roles = {member.role for member in setup.members if member.is_mandatory}
        for role in self._policy.required_roles[degree]:
            if role not in mandatory_roles:
                found.append(
                    _violation(
                        ViolationCode.REQUIRED_ROLE_MISSING,
                        "members",
                        f"a {degree.value} defense needs a mandatory {role.value} member",
                    )
                )
        return found

    def _check_remote_members(self, setup: DefenseSetup) -> list[Violation]:
        remote = [m for m in setup.members if m.attendance is MemberAttendance.REMOTE_ONLY]
        found: list[Violation] = []
        for member in remote:
            if member.role not in self._policy.remote_allowed_roles:
                found.append(
                    _violation(
                        ViolationCode.REMOTE_ROLE_NOT_ALLOWED,
                        f"members.{member.alias}.attendance",
                        f"{member.alias} ({member.role.value}) may not attend remotely",
                    )
                )
        limit = self._policy.max_remote_members
        if len(remote) > limit:
            found.append(
                _violation(
                    ViolationCode.TOO_MANY_REMOTE_MEMBERS,
                    "members",
                    f"at most {limit} remote member(s) allowed; {len(remote)} are remote-only",
                )
            )
        if remote and setup.defense.attendance_mode is AttendanceMode.IN_PERSON:
            found.append(
                _violation(
                    ViolationCode.REMOTE_MEMBER_IN_PERSON_DEFENSE,
                    "attendance_mode",
                    "the defense is in person only, but a member can only attend remotely",
                )
            )
        return found

    def _check_window(self, defense: Defense, now: datetime) -> list[Violation]:
        found: list[Violation] = []
        start, end = defense.window_start, defense.window_end
        inside_one_term = any(
            term.start <= start and end <= term.end for term in self._policy.term_windows
        )
        if not inside_one_term:
            found.append(
                _violation(
                    ViolationCode.WINDOW_OUTSIDE_TERM,
                    "window_start",
                    "the window must lie inside one term window from the policy",
                )
            )
        # state_machine.md -> DRAFT: window_end - now >= notice_days.
        today = local_date(now, self._policy.timezone)
        if (end - today).days < self._policy.notice_days:
            found.append(
                _violation(
                    ViolationCode.WINDOW_TOO_SHORT_FOR_NOTICE,
                    "window_end",
                    f"the window must end at least {self._policy.notice_days} days from today",
                )
            )
        if not any(self._is_allowed_date(day) for day in dates_between(start, end)):
            found.append(
                _violation(
                    ViolationCode.NO_WORKING_DAY_IN_WINDOW,
                    "window_start",
                    "the window has no working day that is inside a term and not a blackout",
                )
            )
        return found

    def _is_allowed_date(self, day: date) -> bool:
        policy = self._policy
        return (
            weekday_of(day) in policy.working_hours.weekdays
            and day not in policy.blackout_dates
            and any(term.start <= day <= term.end for term in policy.term_windows)
        )

    # ------------------------------------------------------------ one slot

    def check_slot(self, defense: Defense, slot: Slot, now: datetime) -> list[Violation]:
        """Every hard rule the slot breaks. An empty list means the slot is allowed.

        Member availability and rooms are NOT checked here (solver, room filter).
        """
        policy = self._policy
        found: list[Violation] = []
        expected = timedelta(minutes=policy.duration_minutes[defense.degree_level])
        if slot.end - slot.start != expected:
            minutes = int(expected.total_seconds() // 60)
            found.append(
                _violation(
                    ViolationCode.WRONG_DURATION,
                    "slot",
                    f"a {defense.degree_level.value} defense lasts {minutes} minutes",
                )
            )

        tz = zone(policy.timezone)
        start_local = slot.start.astimezone(tz)
        end_local = slot.end.astimezone(tz)
        day = start_local.date()
        hours = policy.working_hours
        if weekday_of(day) not in hours.weekdays:
            found.append(_violation(ViolationCode.NOT_A_WORKING_DAY, "slot", "not a working day"))
        within_hours = (
            end_local.date() == day
            and hours.start <= start_local.time()
            and end_local.time() <= hours.end
        )
        if not within_hours:
            found.append(
                _violation(
                    ViolationCode.OUTSIDE_WORKING_HOURS,
                    "slot",
                    f"must be between {hours.start:%H:%M} and {hours.end:%H:%M} local time",
                )
            )
        if day in policy.blackout_dates:
            found.append(_violation(ViolationCode.BLACKOUT_DATE, "slot", "blackout date"))
        if not any(term.start <= day <= term.end for term in policy.term_windows):
            found.append(_violation(ViolationCode.OUTSIDE_TERM, "slot", "outside term dates"))
        if not defense.window_start <= day <= defense.window_end:
            found.append(
                _violation(ViolationCode.OUTSIDE_WINDOW, "slot", "outside the defense window")
            )
        if now > self.notice_deadline(slot):
            found.append(
                _violation(
                    ViolationCode.NOTICE_DEADLINE_PASSED,
                    "slot",
                    f"the {policy.notice_days}-day announcement notice can no longer be met",
                )
            )
        return found

    def notice_deadline(self, slot: Slot) -> datetime:
        """Last moment the announcement can go out: notice_days CALENDAR days before.

        Counted in the university's local time, at the same wall-clock time, so a DST
        change in between does not move it by an hour (a Thursday 10:00 defense with
        14 days' notice -> the Thursday two weeks before, 10:00 local).
        """
        tz_name = self._policy.timezone
        start_wall = slot.start.astimezone(zone(tz_name)).replace(tzinfo=None)
        deadline_wall = start_wall - timedelta(days=self._policy.notice_days)
        return wall_to_utc(deadline_wall, tz_name)


# ---------------------------------------------------------------- helpers


def _violation(code: ViolationCode, field: str, message: str) -> Violation:
    return Violation(code=code, field=field, message=message)


def _duplicates(
    keys: list[str], members: list[CommitteeMember], code: ViolationCode, text: str
) -> list[Violation]:
    """One violation per member whose key was already used by an earlier member."""
    seen: set[str] = set()
    found: list[Violation] = []
    for key, member in zip(keys, members, strict=True):
        if key in seen:
            found.append(_violation(code, f"members.{member.alias}", f"{member.alias} {text}"))
        seen.add(key)
    return found
