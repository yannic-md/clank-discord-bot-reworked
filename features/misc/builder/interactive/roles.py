from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

from discord import Guild, Member, Role

from features.misc.builder.interactive.models import ROLE_ACTIONS, Action, ActionType


class RoleProblem(StrEnum):
    """Why a role must not be handed out by an item. The values double as locale keys of the editor."""

    EVERYONE = "everyone"
    MANAGED = "managed"
    ABOVE_CREATOR = "above_creator"
    ABOVE_BOT = "above_bot"
    CREATOR_MISSING_PERMISSION = "creator_missing_permission"
    BOT_MISSING_PERMISSION = "bot_missing_permission"


def role_problem(role: Role, creator: Member, bot_member: Member) -> RoleProblem | None:
    """Why `creator` may not configure an item that hands out `role`, or `None` if they may.

    Without this check anyone allowed to build messages could hand out - and thereby give
    themselves - roles above their own through the bot.
    """
    if role.is_default():
        return RoleProblem.EVERYONE
    if role.managed:
        return RoleProblem.MANAGED
    if not creator.guild_permissions.manage_roles:
        return RoleProblem.CREATOR_MISSING_PERMISSION
    if not bot_member.guild_permissions.manage_roles:
        return RoleProblem.BOT_MISSING_PERMISSION
    # Only the owner may use roles at or above their own top role.
    if creator.id != creator.guild.owner_id and role >= creator.top_role:
        return RoleProblem.ABOVE_CREATOR
    if role >= bot_member.top_role:
        return RoleProblem.ABOVE_BOT
    return None


def bot_can_manage(role: Role, bot_member: Member) -> bool:
    """Whether the bot can add and remove `role` right now (checked again on every click, as roles move)."""
    return (
        bot_member.guild_permissions.manage_roles
        and not role.is_default()
        and not role.managed
        and role < bot_member.top_role
    )


def referenced_role_ids(actions: Sequence[Action]) -> list[int]:
    """Every role id the role actions mention, once each, in order."""
    seen: dict[int, None] = {}
    for action in actions:
        if action.type in ROLE_ACTIONS:
            for role_id in action.roles:
                seen[role_id] = None
    return list(seen)


@dataclass(frozen=True, slots=True)
class RolePlan:
    """The net role change the actions of an item amount to for one member.

    `skipped` are the mentioned roles the bot cannot handle (deleted, moved above the bot, ...).
    """

    add: tuple[int, ...] = ()
    remove: tuple[int, ...] = ()
    skipped: tuple[int, ...] = ()

    @property
    def changes_anything(self) -> bool:
        """Whether any role has to be added or removed at all."""
        return bool(self.add or self.remove)


def _apply_action(held: set[int], action: Action, manageable: Collection[int], touched: dict[int, None]) -> None:
    """Apply one role action to the roles `held`; roles the bot cannot manage are left alone."""
    roles = [role_id for role_id in action.roles if role_id in manageable]
    touched.update(dict.fromkeys(roles))

    match action.type:
        case ActionType.ROLE_ADD:
            held.update(roles)
        case ActionType.ROLE_REMOVE:
            held.difference_update(roles)
        case ActionType.ROLE_TOGGLE:
            # A bundle is toggled as a whole: taking it away needs every role, otherwise the rest is topped up.
            if roles and all(role_id in held for role_id in roles):
                held.difference_update(roles)
            else:
                held.update(roles)
        case ActionType.ROLE_SET:
            # The chosen roles are all the member keeps. Every other role they hold goes - as far as the bot can
            # manage it: @everyone, integration roles and roles above the bot stay, as they cannot be taken away.
            others = [role_id for role_id in held if role_id in manageable and role_id not in action.roles]
            touched.update(dict.fromkeys(others))
            held.difference_update(others)
            held.update(roles)


def plan_role_actions(held: Collection[int], actions: Sequence[Action], manageable: Collection[int]) -> RolePlan:
    """Work out the net role change of all role actions, applied in order to the roles the member `held`.

    Several actions of one item are merged into a single change, so a role that one action
    adds and a later one removes again is not touched at all.
    """
    current = set(held)
    original = frozenset(held)
    touched: dict[int, None] = {}

    for action in actions:
        if action.type in ROLE_ACTIONS:
            _apply_action(current, action, manageable, touched)

    mentioned = referenced_role_ids(actions)
    return RolePlan(
        add=tuple(role_id for role_id in touched if role_id in current and role_id not in original),
        remove=tuple(role_id for role_id in touched if role_id not in current and role_id in original),
        skipped=tuple(role_id for role_id in mentioned if role_id not in manageable),
    )


def plan_menu_roles(
    held: Collection[int], menu: Sequence[int], selected: Collection[int], manageable: Collection[int]
) -> RolePlan:
    """The net role change of a role dropdown: the selected roles are added, and the roles of the dropdown
    that the member holds but did not select are taken away (so picking another role of a single-choice
    dropdown swaps it). Roles outside the dropdown are never touched; roles the bot cannot manage are skipped."""
    held_set = set(held)
    chosen = [role_id for role_id in menu if role_id in selected]
    return RolePlan(
        add=tuple(role_id for role_id in chosen if role_id in manageable and role_id not in held_set),
        remove=tuple(
            role_id for role_id in menu if role_id in manageable and role_id in held_set and role_id not in selected
        ),
        skipped=tuple(role_id for role_id in dict.fromkeys(menu) if role_id not in manageable),
    )


def resolve_roles(guild: Guild, role_ids: Collection[int]) -> list[Role]:
    """The roles of `guild` for these ids, in order; ids of roles that no longer exist are dropped."""
    roles = (guild.get_role(role_id) for role_id in role_ids)
    return [role for role in roles if role is not None]


async def apply_role_plan(member: Member, plan: RolePlan, *, reason: str) -> None:
    """Carry out `plan` on `member`.

    Raises:
        Forbidden: The bot lacks the permission, or a role moved above it in the meantime.
        HTTPException: Discord rejected the change.
    """
    to_add = resolve_roles(member.guild, plan.add)
    to_remove = resolve_roles(member.guild, plan.remove)

    if to_add:
        await member.add_roles(*to_add, reason=reason)
    if to_remove:
        await member.remove_roles(*to_remove, reason=reason)
