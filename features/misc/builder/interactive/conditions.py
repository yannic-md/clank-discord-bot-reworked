import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from discord import Member

from features.misc.builder.interactive.models import Condition, ConditionType


@dataclass(frozen=True, slots=True)
class ConditionFailure:
    """The first condition a user did not meet. `remaining` is only set for a cooldown (seconds left)."""

    condition: Condition
    remaining: int = 0


class CooldownTracker:
    """In-memory per-key cooldowns. They are short-lived by design, so a restart simply forgets them."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """`clock` returns seconds on a monotonic timeline; tests replace it."""
        self._clock: Callable[[], float] = clock
        self._until: dict[tuple[int, str, int], float] = {}

    def remaining(self, key: tuple[int, str, int]) -> int:
        """Whole seconds (rounded up) until `key` may act again; `0` if it may act now."""
        left = self._until.get(key, 0.0) - self._clock()
        return math.ceil(left) if left > 0 else 0

    def start(self, key: tuple[int, str, int], seconds: int) -> None:
        """Block `key` for `seconds` and forget every cooldown that has already run out."""
        now = self._clock()
        self._until = {known: until for known, until in self._until.items() if until > now}
        self._until[key] = now + seconds


def _has_all_roles(member: Member, role_ids: Sequence[int]) -> bool:
    """Whether `member` has every one of the roles."""
    held = {role.id for role in member.roles}
    return all(role_id in held for role_id in role_ids)


def _has_any_role(member: Member, role_ids: Sequence[int]) -> bool:
    """Whether `member` has at least one of the roles."""
    held = {role.id for role in member.roles}
    return any(role_id in held for role_id in role_ids)


def _is_met(member: Member, condition: Condition, now: datetime) -> bool:
    """Whether `member` meets a condition that can be judged from the member alone."""
    match condition.type:
        case ConditionType.ROLE_REQUIRED:
            return _has_all_roles(member, condition.roles) if condition.match_all else _has_any_role(member, condition.roles)
        case ConditionType.ROLE_FORBIDDEN:
            return not _has_any_role(member, condition.roles)
        case ConditionType.PERMISSIONS:
            granted = member.guild_permissions
            return any(getattr(granted, name, False) for name in condition.permissions)
        case ConditionType.ACCOUNT_AGE:
            return now - member.created_at >= timedelta(days=condition.amount)
        case ConditionType.MEMBER_AGE:
            # A member without a known join date cannot prove their age, so they do not pass.
            return member.joined_at is not None and now - member.joined_at >= timedelta(days=condition.amount)
        case _:
            # "Once per user" and cooldowns need state, which the caller owns.
            return True


def check_conditions(
    member: Member, conditions: Sequence[Condition], *, now: datetime | None = None
) -> ConditionFailure | None:
    """The first condition `member` does not meet, or `None` if they meet all of those judged from the member.

    Conditions that need state (`ONCE_PER_USER`, `COOLDOWN`) are skipped here; the click handler checks them.
    """
    moment = now or datetime.now(UTC)
    for condition in conditions:
        if not _is_met(member, condition, moment):
            return ConditionFailure(condition)
    return None
