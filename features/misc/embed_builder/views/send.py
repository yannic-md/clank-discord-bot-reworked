from discord import (
    AllowedMentions,
    ButtonStyle,
    ClientUser,
    Colour,
    Embed,
    Forbidden,
    Guild,
    HTTPException,
    Interaction,
    Member,
    Message,
    NotFound,
    Permissions,
    Role,
    Thread,
    Webhook,
    WebhookMessage,
)
from discord.abc import GuildChannel, Messageable
from discord.ui import Button, button
from discord.utils import MISSING

from core.discord_api.limits import MAX_WEBHOOK_COUNT
from core.i18n.translator import lookup, translate
from features.misc.embed_builder.modals.webhook import WEBHOOK_LIMIT_ERROR_CODE, find_webhook
from features.misc.embed_builder.session import BuilderSession, WebhookSender
from features.misc.embed_builder.util.embed_ops import non_empty_embeds
from features.misc.embed_builder.validation import (
    append_error,
    check_for_mention_perms,
    count_user_mentions,
    describe_role_mentions,
    get_channel_placeholder,
    get_role_mention_count,
    is_everyone_mentioned,
)
from features.misc.embed_builder.views.base import (
    BuilderScreenView,
    build_allowed_mentions,
    create_success_embed,
    has_message_content,
    show,
)


class SendConfirmView(BuilderScreenView):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session
        channel: GuildChannel | Thread = session.target_channel
        description: str = translate(session.language, "builder.info.send_confirm.description", channel=channel.mention)

        if session.webhook.enabled:
            webhook_name: str = session.webhook.username or session.webhook.display_name or "—"
            description += "\n" + translate(
                session.language, "builder.info.send_confirm.webhook_notice", username=webhook_name
            )

        has_permission: bool = channel.permissions_for(session.slashcmd_author).mention_everyone
        needs_permission: bool = check_for_mention_perms(session.content, session.embeds)
        if needs_permission and not has_permission:
            description += "\n" + translate(session.language, "builder.info.send_confirm.mention_permission_warning")

        # If the permission warning above already fired, showing "the following will be
        # pinged" right below it would contradict it - those mentions won't notify anyone.
        mention_lines: list[str] = []
        if has_permission:
            guild: Guild | None = channel.guild if isinstance(channel, Messageable) else None
            if is_everyone_mentioned(session.content):
                users: str = get_role_mention_count(session.language, session.content, guild)
                mention_lines.append(translate(session.language, "builder.info.send_confirm.everyone_notice", users=users))

            roles: list[Role] = describe_role_mentions(session.content, guild) if guild is not None else []
            if roles:
                role_list = "\n> - ".join(f"{role.mention} (`{len(role.members)}` User)" for role in roles)
                mention_lines.append(translate(session.language, "builder.info.send_confirm.roles_notice", roles=role_list))

        user_count: str | None = count_user_mentions(session.language, session.content)
        if user_count is not None:
            mention_lines.append(translate(session.language, "builder.info.send_confirm.mentions_notice", amount=user_count))

        if mention_lines:
            description += "\n" + "\n".join(mention_lines)

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.send_confirm.title"),
            description=description,
            colour=Colour.blurple(),
        )

        if session.webhook.enabled and session.webhook.avatar_url:
            self.info_embed.set_thumbnail(url=session.webhook.avatar_url)

        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]

        self.confirm_button.label = translate(session.language, "builder.buttons.confirm_yes")
        self.confirm_button.emoji = "✅"
        self.cancel_button.label = translate(session.language, "builder.buttons.confirm_no")
        self.cancel_button.emoji = "✏️"

    @button(label="Confirm", style=ButtonStyle.green, row=0, custom_id="embed_builder:send:confirm")
    async def confirm_button(self: SendConfirmView, interaction: Interaction, _button: Button) -> None:
        session: BuilderSession = self.session
        channel: GuildChannel | Thread = session.target_channel
        if not await has_message_content(interaction, session, self):
            return

        if not await _has_user_channel_send_perms(interaction, session, channel, self):
            return

        embeds: list[Embed] = non_empty_embeds(session.embeds)
        if not await _has_bot_channel_send_perms(interaction, session, channel, self, has_embeds=bool(embeds)):
            return

        assert isinstance(interaction.user, Member)
        allowed: AllowedMentions = build_allowed_mentions(channel, interaction.user)
        if session.webhook.enabled:
            sent = await _send_via_webhook(interaction, channel, session, interaction.client.user, allowed, embeds, self)
            if sent is None:
                return

            jump_url: str | None = sent.jump_url
        else:
            assert isinstance(channel, Messageable)
            sent_message: Message = await channel.send(
                content=session.message_content, embeds=embeds, allowed_mentions=allowed
            )
            jump_url = sent_message.jump_url

        self.stop()
        if channel.id == session.slashcmd_channel.id:
            jump_url = None

        success_embed: Embed = create_success_embed(session, "builder.info.success.sent", jump_url=jump_url)
        await interaction.response.edit_message(content=None, embeds=[success_embed], view=None)

    @button(label="Cancel", style=ButtonStyle.gray, row=0, custom_id="embed_builder:send:cancel")
    async def cancel_button(self: SendConfirmView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))


async def save_message_changes(interaction: Interaction, session: BuilderSession, view: BuilderScreenView) -> None:
    assert session.target_message is not None
    channel = session.target_message.channel
    assert isinstance(channel, GuildChannel | Thread)

    if not await has_message_content(interaction, session, view):
        return

    embeds: list[Embed] = non_empty_embeds(session.embeds)
    if not await _has_bot_channel_send_perms(interaction, session, channel, view, has_embeds=bool(embeds)):
        return

    allowed: AllowedMentions = build_allowed_mentions(channel, interaction.user)  # type: ignore[arg-type]
    await session.target_message.edit(content=session.message_content, embeds=embeds, allowed_mentions=allowed)

    view.stop()
    success_embed: Embed = create_success_embed(session, "builder.info.success.saved")
    await interaction.response.edit_message(content=None, embeds=[success_embed], view=None)


async def _send_via_webhook(
    interaction: Interaction,
    channel: GuildChannel | Thread,
    session: BuilderSession,
    bot_user: ClientUser | None,
    allowed: AllowedMentions,
    embeds: list[Embed],
    view: BuilderScreenView,
) -> WebhookMessage | None:
    """Send the message via the session's webhook identity.

    Returns None (after already responding with a translated error) if the bot lacks
    `manage_webhooks`, the channel's webhook limit is reached, or the cached webhook was
    deleted since it was last validated - the sent `WebhookMessage` on success.
    """
    webhook: Webhook

    # An explicitly pasted webhook URL is always reused as-is; an auto-resolved one is
    # only trusted for the channel it was validated for, and re-resolved otherwise.
    if session.webhook.webhook_url is not None and (
        session.webhook.explicit_url or session.webhook.validated_channel_id == channel.id
    ):
        webhook = Webhook.from_url(session.webhook.webhook_url, client=interaction.client)
    else:
        try:
            webhook = await find_webhook(channel, session.webhook.username, bot_user)
        except Forbidden:
            channel_ref: str = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
            message: str = translate(session.language, "builder.errors.webhook_forbidden", channel=channel_ref)
            await append_error(interaction, view.embeds, view, message)
            return None

        except HTTPException as error:
            if error.code != WEBHOOK_LIMIT_ERROR_CODE:
                raise

            channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
            message = translate(
                session.language, "builder.errors.webhook_limit", channel=channel_ref, limit=MAX_WEBHOOK_COUNT
            )
            await append_error(interaction, view.embeds, view, message)
            return None

    # Only override the webhook's own name/avatar if the user explicitly set one -
    # a webhook reused via URL (or by name) otherwise keeps its own configured identity.
    # MISSING (discord.py's "not provided" sentinel) is passed for anything unset, so the
    # call can be made directly instead of building a kwargs dict.
    try:
        return await webhook.send(
            embeds=embeds,
            allowed_mentions=allowed,
            wait=True,
            username=session.webhook.username or MISSING,
            avatar_url=session.webhook.avatar_url or MISSING,
            content=session.content or MISSING,
            thread=channel if isinstance(channel, Thread) else MISSING,
        )
    except NotFound:
        # The webhook is gone - stop treating it as a configured identity going forward.
        session.webhook = WebhookSender()
        message = translate(session.language, "builder.errors.webhook_invalid")
        await append_error(interaction, view.embeds, view, message)
        return None


async def _has_bot_channel_send_perms(
    interaction: Interaction,
    session: BuilderSession,
    channel: GuildChannel | Thread,
    view: BuilderScreenView,
    *,
    has_embeds: bool,
) -> bool:
    """Pre-flight check of the bot's own permissions in `channel`, so a missing-permission
    failure names the exact permission instead of falling back to a generic error."""
    guild: Guild | None = channel.guild if isinstance(channel, Messageable) else None
    bot_member: Member | None = guild.me if guild is not None else None
    if bot_member is None:
        return True

    permissions: Permissions = channel.permissions_for(bot_member)
    required: list[str] = ["view_channel", "send_messages", *(["embed_links"] if has_embeds else [])]
    missing: list[str] = [perm for perm in required if not getattr(permissions, perm)]
    if not missing:
        return True

    permission_names: str = format_missing_permissions(session, missing)
    message: str = translate(
        session.language,
        "builder.errors.bot_permission_missing",
        channel=get_channel_placeholder(session.language, channel, session.slashcmd_channel.id),
        permissions=permission_names,
    )

    await append_error(interaction, view.embeds, view, message)
    return False


async def _has_user_channel_send_perms(
    interaction: Interaction, session: BuilderSession, channel: GuildChannel | Thread, view: BuilderScreenView
) -> bool:
    """Pre-flight check that the invoking user can actually see and post in `channel` themselves -
    otherwise the bot would let them post into a channel they have no access to at all."""
    permissions: Permissions = channel.permissions_for(interaction.user)  # type: ignore[arg-type]
    required: list[str] = ["view_channel", "send_messages"]
    missing: list[str] = [perm for perm in required if not getattr(permissions, perm)]
    if not missing:
        return True

    permission_names: str = format_missing_permissions(session, missing)
    message: str = translate(
        session.language,
        "builder.errors.user_permission_missing",
        channel=get_channel_placeholder(session.language, channel, session.slashcmd_channel.id),
        permissions=permission_names,
    )

    await append_error(interaction, view.embeds, view, message)
    return False


def format_missing_permissions(session: BuilderSession, permissions: list[str]) -> str:
    """Creates a commad separated list to show the user all missing permissions."""
    return ", ".join((lookup(session.language, f"errors.permissions.{perm}") or perm).upper() for perm in permissions)
