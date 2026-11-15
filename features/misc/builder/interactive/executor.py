import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from logging import Logger

from discord import AllowedMentions, Forbidden, HTTPException, Interaction, Member, NotFound
from discord.abc import Messageable
from discord.utils import MISSING

from core.enums.language import SupportedLanguage
from features.misc.builder.channels import can_post_in, find_channel
from features.misc.builder.interactive.messages import role_plan_text, t
from features.misc.builder.interactive.models import MESSAGE_ACTIONS, ROLE_ACTIONS, Action, ActionType
from features.misc.builder.interactive.payload import OutgoingMessage, build_outgoing
from features.misc.builder.interactive.roles import (
    RolePlan,
    apply_role_plan,
    bot_can_manage,
    plan_menu_roles,
    plan_role_actions,
    referenced_role_ids,
    resolve_roles,
)

logger: Logger = logging.getLogger("discord")


@dataclass
class ClickContext:
    """Who used which button or dropdown, and in which language to answer."""

    interaction: Interaction
    member: Member
    language: SupportedLanguage
    answers: Sequence[tuple[str, str]] = ()
    """The (question, answer) pairs of a submitted form, for the placeholders of its messages."""


@dataclass
class ExecutionResult:
    """What running actions produced: the text to tell the user (possibly empty) and whether a reply was sent."""

    text: str = ""
    replied: bool = False
    lines: list[str] = field(default_factory=list)
    """What went wrong (a message that could not be sent, ...), one line each."""
    confirmations: list[str] = field(default_factory=list)
    """What went through without the user seeing it happen (a private message, a message in a channel, the deleted
    message), one line each - a reply of the item replaces them, as it answers for the item itself."""


def _mention_rules(member: Member) -> AllowedMentions:
    """A message sent because of a click may ping the person who clicked - and nobody else."""
    return AllowedMentions(everyone=False, roles=False, users=[member], replied_user=False)


def _manageable_roles(member: Member, role_ids: Sequence[int]) -> set[int]:
    """Which of the roles the bot can add and remove right now."""
    guild = member.guild
    return {role.id for role in resolve_roles(guild, role_ids) if bot_can_manage(role, guild.me)}


async def _send(destination: Messageable, message: OutgoingMessage, member: Member) -> None:
    """Send a payload's message to a channel or a person."""
    if message.view is not None:
        await destination.send(view=message.view, allowed_mentions=_mention_rules(member))
        return

    await destination.send(
        content=message.content or MISSING, embeds=message.embeds or MISSING, allowed_mentions=_mention_rules(member)
    )


async def _reply(click: ClickContext, action: Action) -> str | None:
    """Answer the click with the action's message, visible to the user only. The error line, if it fails."""
    interaction = click.interaction
    assert interaction.guild is not None
    if action.payload is None:  # a stored action without its message (a damaged or hand-edited row)
        return t(click.language, "result.message_unavailable")
    message = build_outgoing(
        action.payload, member=click.member, guild=interaction.guild, channel=interaction.channel, answers=click.answers
    )
    if message is None:
        return t(click.language, "result.message_unavailable")

    if message.view is not None:
        await interaction.followup.send(view=message.view, ephemeral=True, allowed_mentions=AllowedMentions.none())
        return None

    await interaction.followup.send(
        content=message.content or MISSING,
        embeds=message.embeds or MISSING,
        ephemeral=True,
        allowed_mentions=AllowedMentions.none(),
    )
    return None


async def _direct_message(click: ClickContext, action: Action) -> str | None:
    """Send the action's message to the user privately. The error line, if it fails."""
    interaction = click.interaction
    assert interaction.guild is not None
    if action.payload is None:
        return t(click.language, "result.message_unavailable")
    message = build_outgoing(
        action.payload, member=click.member, guild=interaction.guild, channel=interaction.channel, answers=click.answers
    )
    if message is None:
        return t(click.language, "result.message_unavailable")

    try:
        await _send(click.member, message, click.member)
    except Forbidden, HTTPException:
        return t(click.language, "result.dm_failed")
    return None


async def _channel_message(click: ClickContext, action: Action) -> str | None:
    """Post the action's message in the chosen channel. The error line, if it fails."""
    interaction = click.interaction
    guild = interaction.guild
    assert guild is not None
    if action.payload is None:
        return t(click.language, "result.message_unavailable")
    if action.channel_id is None:  # a stored action without its channel
        return t(click.language, "result.channel_gone")
    channel = await find_channel(guild, action.channel_id)
    if channel is None or not isinstance(channel, Messageable):
        return t(click.language, "result.channel_gone")

    if not can_post_in(channel, guild.me):
        return t(click.language, "result.channel_forbidden", channel=channel.mention)

    message = build_outgoing(action.payload, member=click.member, guild=guild, channel=channel, answers=click.answers)
    if message is None:
        return t(click.language, "result.message_unavailable")

    try:
        await _send(channel, message, click.member)
    except Forbidden, HTTPException:
        return t(click.language, "result.channel_failed", channel=channel.mention)
    return None


async def _delete_message(click: ClickContext) -> str | None:
    """Delete the message the button or dropdown sits on. The error line, if it fails."""
    message = click.interaction.message
    if message is None:
        return None

    try:
        await message.delete()
    except Forbidden, NotFound, HTTPException:
        return t(click.language, "result.delete_failed")
    return None


async def execute_actions(
    click: ClickContext, actions: Sequence[Action], *, reason: str, restricted: bool
) -> ExecutionResult:
    """Run the actions of a button or dropdown option for the user who used it.

    The role actions are merged into one net change and applied first, so a role one action adds and a later one
    removes again is never touched. The messages follow in the order the actions are listed, and deleting the
    message always comes last. A reply replaces the automatic summary of the role change, as it says it better.

    `restricted` tells whether use is limited to chosen people; deleting the message is refused otherwise.

    Raises:
        Forbidden: The bot lacks the permission for the role change.
        HTTPException: Discord rejected the role change.
    """
    if not actions:
        return ExecutionResult(text=t(click.language, "result.no_actions"))

    result = ExecutionResult()
    role_actions = [action for action in actions if action.type in ROLE_ACTIONS]
    role_text = ""
    if role_actions:
        candidates = referenced_role_ids(role_actions)
        if any(action.type is ActionType.ROLE_SET for action in role_actions):
            candidates += [role.id for role in click.member.roles]  # "set" takes away whatever else they hold
        manageable = _manageable_roles(click.member, candidates)
        plan = plan_role_actions({role.id for role in click.member.roles}, role_actions, manageable)
        await apply_role_plan(click.member, plan, reason=reason)
        role_text = role_plan_text(click.language, plan)

    for action in actions:
        if action.type not in MESSAGE_ACTIONS:  # roles are done, deleting follows, a form is not run here
            continue
        confirmation: str | None = None
        if action.type is ActionType.REPLY:
            problem = await _reply(click, action)
            result.replied = result.replied or problem is None
        elif action.type is ActionType.DM_USER:
            problem = await _direct_message(click, action)
            confirmation = t(click.language, "result.dm_sent")
        else:
            problem = await _channel_message(click, action)
            confirmation = t(click.language, "result.channel_sent", channel=f"<#{action.channel_id}>")
        if problem is not None:
            result.lines.append(problem)
        elif confirmation is not None:
            result.confirmations.append(confirmation)

    if any(action.type is ActionType.DELETE_MESSAGE for action in actions):
        problem = await _delete_message(click) if restricted else t(click.language, "result.delete_not_allowed")
        if problem is not None:
            result.lines.append(problem)
        else:
            result.confirmations.append(t(click.language, "result.deleted"))

    result.text = _summary(click.language, result, role_text=role_text)
    return result


def _summary(language: SupportedLanguage, result: ExecutionResult, *, role_text: str) -> str:
    """The text that tells the user what happened - nothing if their own reply already did.

    Every action says what it did: the role change, the message that was sent (and where), the message that was
    deleted - and what went wrong. A reply takes over from the first three, but never hides a problem."""
    parts: list[str] = []
    if not result.replied:
        if role_text:
            parts.append(role_text)
        parts.extend(result.confirmations)
    parts.extend(result.lines)
    if not parts and not result.replied:  # only actions that run elsewhere (a form is opened by the click itself)
        parts.append(t(language, "result.no_actions"))
    return "\n".join(parts)


async def execute_role_menu(
    click: ClickContext, menu: Sequence[int], selected: Sequence[int], *, reason: str
) -> ExecutionResult:
    """Apply the choice made in a role dropdown: the selected roles are added, the other roles of the dropdown that
    the user holds are taken away.

    Raises:
        Forbidden: The bot lacks the permission for the role change.
        HTTPException: Discord rejected the role change.
    """
    manageable = _manageable_roles(click.member, menu)
    plan: RolePlan = plan_menu_roles({role.id for role in click.member.roles}, menu, selected, manageable)
    await apply_role_plan(click.member, plan, reason=reason)
    return ExecutionResult(text=role_plan_text(click.language, plan))
