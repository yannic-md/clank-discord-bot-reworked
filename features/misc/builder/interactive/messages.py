from collections.abc import Iterable

from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.interactive.conditions import ConditionFailure
from features.misc.builder.interactive.models import ConditionType
from features.misc.builder.interactive.roles import RolePlan, RoleProblem

_DOMAIN: str = "builder.interactive"


def t(language: SupportedLanguage, key: str, /, count: int | None = None, **variables: object) -> str:
    """Translate a key of the interactive builder's locale domain."""
    return translate(language, f"{_DOMAIN}.{key}", count=count, **variables)


def screen(language: SupportedLanguage, key: str, /, count: int | None = None, **variables: object) -> str:
    """Translate a text of the button and dropdown screens (`screens.*`). Both builders show these screens and say
    the same on them, so the texts live here once: only what differs between the builders (where a button may be
    placed) is in their own locale."""
    return t(language, f"screens.{key}", count=count, **variables)


def _mentions(role_ids: Iterable[int]) -> str:
    """Role mentions of the ids, separated by commas."""
    return ", ".join(f"<@&{role_id}>" for role_id in role_ids)


def permission_names(language: SupportedLanguage, permissions: Iterable[str]) -> str:
    """The permissions as Discord names them, each in capitals as a code span - `MANAGE SERVER`, `ADMINISTRATOR` -,
    separated by commas."""
    names = (translate(language, f"errors.permissions.{name}").upper().replace("`", "'") for name in permissions)
    return ", ".join(f"`{name}`" for name in names)


def condition_failure_text(language: SupportedLanguage, failure: ConditionFailure) -> str:
    """The explanation shown to a user who may not use an item, naming what they would need."""
    condition = failure.condition

    match condition.type:
        case ConditionType.ROLE_REQUIRED:
            key = "conditions.role_required.all" if condition.match_all else "conditions.role_required.any"
            return t(language, key, count=len(condition.roles), roles=_mentions(condition.roles))
        case ConditionType.ROLE_FORBIDDEN:
            return t(language, "conditions.role_forbidden", count=len(condition.roles), roles=_mentions(condition.roles))
        case ConditionType.PERMISSIONS:
            return t(language, "conditions.permissions", permissions=permission_names(language, condition.permissions))
        case ConditionType.ACCOUNT_AGE:
            return t(language, "conditions.account_age", count=condition.amount)
        case ConditionType.MEMBER_AGE:
            return t(language, "conditions.member_age", count=condition.amount)
        case ConditionType.ONCE_PER_USER:
            return t(language, "conditions.once_per_user")
        case ConditionType.COOLDOWN:
            return t(language, "conditions.cooldown", count=failure.remaining)


def role_plan_text(language: SupportedLanguage, plan: RolePlan) -> str:
    """The summary of a role change, one line per kind of change; empty if there is nothing to report."""
    lines: list[str] = []
    if plan.add:
        lines.append(t(language, "result.added", count=len(plan.add), roles=_mentions(plan.add)))
    if plan.remove:
        lines.append(t(language, "result.removed", count=len(plan.remove), roles=_mentions(plan.remove)))
    if plan.skipped:
        lines.append(t(language, "result.skipped", count=len(plan.skipped), roles=_mentions(plan.skipped)))
    if not lines:
        lines.append(t(language, "result.nothing_changed"))
    return "\n".join(lines)


def role_problem_text(language: SupportedLanguage, problem: RoleProblem, role_id: int) -> str:
    """Why the role may not be used by an item, for the editor."""
    return t(language, f"roles.{problem.value}", role=f"<@&{role_id}>")
