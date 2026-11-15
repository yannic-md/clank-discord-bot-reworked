from discord import (
    AllowedMentions,
    ButtonStyle,
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
from core.i18n.translator import translate
from features.misc.builder.discord_errors import send_problem_text
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.embed_ops import non_empty_embeds
from features.misc.builder.embed.util.placement import build_view, placed_item_ids
from features.misc.builder.embed.validation import (
    append_error,
    check_for_mention_perms,
    count_user_mentions,
    describe_role_mentions,
    get_role_mention_count,
    has_room_for_error,
    is_everyone_mentioned,
    text_limit_problem,
    text_over_limit,
)
from features.misc.builder.embed.views.base import (
    BuilderScreenView,
    create_success_embed,
    has_message_content,
    show,
    track_active_view,
)
from features.misc.builder.formatting import format_number
from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.store import Persisted, attach, persist_items, rollback
from features.misc.builder.interactive.ui import sendable_problem
from features.misc.builder.session import WebhookSender
from features.misc.builder.validation import (
    build_allowed_mentions,
    format_missing_permissions,
    get_channel_placeholder,
)
from features.misc.builder.webhook import WEBHOOK_LIMIT_ERROR_CODE, identity_kwargs, resolve_send_webhook


class SendConfirmView(BuilderScreenView):
    """Screen asking the user to confirm sending the message, with a preview of it."""

    def __init__(self, session: BuilderSession) -> None:
        """Describe the target channel, webhook and mentions the message will notify."""
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
                mention_lines.append(
                    translate(session.language, "builder.embed.info.send_confirm.everyone_notice", users=users)
                )

            roles: list[Role] = describe_role_mentions(session.content, guild) if guild is not None else []
            if roles:
                role_list = "\n> - ".join(f"{role.mention} (`{len(role.members)}` User)" for role in roles)
                mention_lines.append(
                    translate(session.language, "builder.embed.info.send_confirm.roles_notice", roles=role_list)
                )

        user_count: int | None = count_user_mentions(session.content)
        if user_count is not None:
            mention_lines.append(
                translate(
                    session.language,
                    "builder.embed.info.send_confirm.mentions_notice",
                    count=user_count,
                    amount=format_number(session.language, user_count),
                )
            )

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

    @button(label="Confirm", style=ButtonStyle.green, row=0, custom_id="embed:send:confirm")
    async def confirm_button(self: SendConfirmView, interaction: Interaction, _button: Button) -> None:
        """Check permissions on the target channel, send the message and report the result."""
        session: BuilderSession = self.session
        channel: GuildChannel | Thread = session.target_channel
        if not await has_message_content(interaction, session, self):
            return

        if not await _has_user_channel_send_perms(interaction, session, channel, self):
            return

        embeds: list[Embed] = non_empty_embeds(session.embeds)
        if not await _fits_text_limit(interaction, session, self, embeds):
            return

        if not await _has_bot_channel_send_perms(interaction, session, channel, self, has_embeds=bool(embeds)):
            return

        placed: list[ItemDraft] = placed_drafts(session)
        if session.webhook.enabled and any(not draft.is_link for draft in placed):
            # Buttons that run actions cannot be sent through a webhook - the editor keeps them out, so this
            # is only a safety net.
            message: str = translate(session.language, "builder.embed.errors.placement_webhook")
            await append_error(interaction, self.embeds, self, message)
            return

        unsendable = sendable_problem(session.language, placed, session.library)
        if unsendable is not None:
            await append_error(interaction, self.embeds, self, unsendable)
            return

        assert isinstance(interaction.user, Member)
        allowed: AllowedMentions = build_allowed_mentions(channel, interaction.user)
        persisted: Persisted = await persist_items(
            session.library, placed, guild_id=session.guild_id, creator_id=session.slashcmd_author_id
        )
        jump_url: str | None
        try:
            if session.webhook.enabled:
                sent = await _send_via_webhook(interaction, channel, session, allowed, embeds, self)
                if sent is None:
                    await rollback(session.library, persisted)
                    return

                sent_id, sent_channel_id, jump_url = sent.id, sent.channel.id, sent.jump_url
            else:
                assert isinstance(channel, Messageable)
                sent_message: Message = await channel.send(
                    content=session.message_content,
                    embeds=embeds,
                    allowed_mentions=allowed,
                    view=build_view(session) or MISSING,
                )
                sent_id, sent_channel_id, jump_url = sent_message.id, sent_message.channel.id, sent_message.jump_url

        except HTTPException as error:
            await rollback(session.library, persisted)
            problem = send_problem_text(session.language, error)
            if problem is None:
                raise

            await append_error(interaction, self.embeds, self, problem)
            return

        except BaseException:
            await rollback(session.library, persisted)
            raise

        await attach(session.library, persisted, channel_id=sent_channel_id, message_id=sent_id)

        self.stop()
        if channel.id == session.slashcmd_channel.id:
            jump_url = None

        success_embed: Embed = create_success_embed(session, "builder.info.success.sent", jump_url=jump_url)
        await interaction.response.edit_message(content=None, embeds=[success_embed], view=None)

    @button(label="Cancel", style=ButtonStyle.gray, row=0, custom_id="embed:send:cancel")
    async def cancel_button(self: SendConfirmView, interaction: Interaction, _button: Button) -> None:
        """Go back to the main screen without sending."""
        from features.misc.builder.embed.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))


async def save_message_changes(interaction: Interaction, session: BuilderSession, view: BuilderScreenView) -> None:
    """Write the current content and embeds back to the message that is being edited."""
    assert session.target_message is not None
    channel = session.target_message.channel
    assert isinstance(channel, GuildChannel | Thread)

    if not await has_message_content(interaction, session, view):
        return

    embeds: list[Embed] = non_empty_embeds(session.embeds)
    if not await _fits_text_limit(interaction, session, view, embeds):
        return

    if not await _has_bot_channel_send_perms(interaction, session, channel, view, has_embeds=bool(embeds)):
        return

    placed: list[ItemDraft] = placed_drafts(session)
    unsendable = sendable_problem(session.language, placed, session.library)
    if unsendable is not None:
        await append_error(interaction, view.embeds, view, unsendable)
        return

    allowed: AllowedMentions = build_allowed_mentions(channel, interaction.user)  # type: ignore[arg-type]
    persisted: Persisted = await persist_items(
        session.library, placed, guild_id=session.guild_id, creator_id=session.slashcmd_author_id
    )
    try:
        await session.target_message.edit(
            content=session.message_content, embeds=embeds, allowed_mentions=allowed, view=build_view(session)
        )
    except NotFound:
        await rollback(session.library, persisted)
        await _restore_send_mode(interaction, session)
        return

    except HTTPException as error:
        await rollback(session.library, persisted)
        problem = send_problem_text(session.language, error)
        if problem is None:
            raise

        await append_error(interaction, view.embeds, view, problem)
        return

    except BaseException:
        await rollback(session.library, persisted)
        raise

    await attach(session.library, persisted, channel_id=channel.id, message_id=session.target_message.id)

    view.stop()
    success_embed: Embed = create_success_embed(session, "builder.info.success.saved")
    await interaction.response.edit_message(content=None, embeds=[success_embed], view=None)


async def _fits_text_limit(
    interaction: Interaction, session: BuilderSession, view: BuilderScreenView, embeds: list[Embed]
) -> bool:
    """Whether the embeds hold no more text than one message may (6000 characters). The editor keeps every change
    within it, so only a stored template or an imported message could get here with too much - say so instead of
    sending what Discord refuses."""
    over: int = text_over_limit(embeds)
    if not over:
        return True

    await append_error(interaction, view.embeds, view, text_limit_problem(session.language, over))
    return False


def placed_drafts(session: BuilderSession) -> list[ItemDraft]:
    """The buttons that sit in the message's rows, in the order they appear."""
    drafts = (session.library.get(item_id) for item_id in placed_item_ids(session))
    return [draft for draft in drafts if draft is not None]


async def _restore_send_mode(interaction: Interaction, session: BuilderSession) -> None:
    """The message being edited was deleted meanwhile: drop edit mode so the builder works as a
    fresh "send a new message" session again (send button, webhook, channel), keeping all content."""
    from features.misc.builder.embed.views.gui import EmbedBuilderGUI

    for draft in session.library.items.values():
        draft.db_id = None
    session.library.loaded_db_ids.clear()
    session.edit_mode = False
    session.target_message = None

    gui: EmbedBuilderGUI = EmbedBuilderGUI(session)
    track_active_view(gui)

    message: str = translate(session.language, "builder.errors.message_deleted")
    # Appending the error as one more embed is impossible at Discord's embed or text cap - then it is sent separately.
    fits: bool = has_room_for_error(gui.embeds, message)
    embeds: list[Embed] = [*gui.embeds, Embed(description=message, colour=Colour.red())] if fits else gui.embeds
    await interaction.response.edit_message(content=gui.content, embeds=embeds, view=gui)
    gui.message = await interaction.original_response()
    if not fits:
        await interaction.followup.send(message, ephemeral=True)


async def _send_via_webhook(
    interaction: Interaction,
    channel: GuildChannel | Thread,
    session: BuilderSession,
    allowed: AllowedMentions,
    embeds: list[Embed],
    view: BuilderScreenView,
) -> WebhookMessage | None:
    """Send the message via the session's webhook identity.

    Returns None (after already responding with a translated error) if the bot lacks
    `manage_webhooks`, the channel's webhook limit is reached, or the cached webhook was
    deleted since it was last validated - the sent `WebhookMessage` on success.
    """
    try:
        webhook: Webhook = await resolve_send_webhook(interaction.client, channel, session.webhook)
    except Forbidden:
        channel_ref: str = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
        message: str = translate(session.language, "builder.errors.webhook_forbidden", channel=channel_ref)
        await append_error(interaction, view.embeds, view, message)
        return None

    except HTTPException as error:
        if error.code != WEBHOOK_LIMIT_ERROR_CODE:
            raise

        channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
        message = translate(session.language, "builder.errors.webhook_limit", channel=channel_ref, limit=MAX_WEBHOOK_COUNT)
        await append_error(interaction, view.embeds, view, message)
        return None

    try:
        return await webhook.send(
            embeds=embeds,
            allowed_mentions=allowed,
            wait=True,
            content=session.content or MISSING,
            view=build_view(session) or MISSING,
            **identity_kwargs(session.webhook, channel),
        )
    except HTTPException as error:
        if error.status not in (401, 404):  # 404: the webhook is gone; 401: its token is wrong
            raise
        # The webhook cannot be used - stop treating it as a configured identity going forward.
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

    permission_names: str = format_missing_permissions(session.language, missing)
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

    permission_names: str = format_missing_permissions(session.language, missing)
    message: str = translate(
        session.language,
        "builder.errors.user_permission_missing",
        channel=get_channel_placeholder(session.language, channel, session.slashcmd_channel.id),
        permissions=permission_names,
    )

    await append_error(interaction, view.embeds, view, message)
    return False
