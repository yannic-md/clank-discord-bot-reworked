from discord import (
    AllowedMentions,
    ButtonStyle,
    Colour,
    HTTPException,
    Interaction,
    Member,
    Message,
    NotFound,
    Thread,
    WebhookMessage,
)
from discord.abc import GuildChannel, Messageable
from discord.ui import ActionRow

from core.discord_api.limits import MAX_V2_TOTAL_TEXT_LENGTH
from core.enums.language import SupportedLanguage
from features.misc.builder.container.models import ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.placement import placed_item_ids
from features.misc.builder.container.util.render import (
    StaticLayoutView,
    final_items,
    preview_items,
    text_message_view,
)
from features.misc.builder.container.util.tree import non_empty_nodes, total_text_length
from features.misc.builder.container.util.webhook import send_via_webhook
from features.misc.builder.container.validation import contains_mass_mention, missing_send_permissions
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, info_container, show
from features.misc.builder.discord_errors import send_problem_text
from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.store import Persisted, attach, persist_items, rollback
from features.misc.builder.interactive.ui import sendable_problem
from features.misc.builder.validation import (
    build_allowed_mentions,
    format_missing_permissions,
    get_channel_placeholder,
)


class SendConfirmView(BuilderLayoutView):
    """Screen asking the user to confirm sending the message, with a preview of it."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error box to show."""
        from features.misc.builder.container.views.gui import MainView

        super().__init__()
        self.session = session

        nodes = non_empty_nodes(session.components)
        for item in preview_items(session, nodes):
            self.add_preview(item)

        member = session.slashcmd_author
        channel = session.target_channel
        has_mention_permission = channel.permissions_for(member).mention_everyone

        info_lines = [
            f"### {ts(session.language, 'info.send_confirm.title')}",
            ts(session.language, "info.send_confirm.description", channel=channel.mention),
        ]
        if session.webhook.enabled:
            webhook_name = session.webhook.username or session.webhook.display_name or "—"
            info_lines.append(ts(session.language, "info.send_confirm.webhook_notice", username=webhook_name))
        if contains_mass_mention(nodes) and not has_mention_permission:
            info_lines.append(ts(session.language, "info.send_confirm.mention_permission_warning"))
        self.add_item(info_container("\n".join(info_lines)))

        nav_row: ActionRow = ActionRow()

        async def on_confirm(interaction: Interaction) -> None:
            """Check permissions on the target channel, send the message and report the result."""
            if not nodes:
                await show(interaction, MainView(session))
                return

            language = session.language
            channel_ref = get_channel_placeholder(language, channel, session.slashcmd_channel.id)

            missing = missing_send_permissions(channel, member)
            if missing:
                permissions = format_missing_permissions(language, missing)
                user_problem = ts(language, "errors.user_permission_missing", channel=channel_ref, permissions=permissions)
                await show(interaction, SendConfirmView(session, error=user_problem))
                return

            missing = missing_send_permissions(channel, channel.guild.me)
            if missing:
                permissions = format_missing_permissions(language, missing)
                bot_problem = ts(language, "errors.bot_permission_missing", channel=channel_ref, permissions=permissions)
                await show(interaction, SendConfirmView(session, error=bot_problem))
                return

            placed = _placed_drafts(session, nodes)
            if session.webhook.enabled and any(not draft.is_link for draft in placed):
                # Buttons that run actions cannot be sent through a webhook - the editor keeps them out, so this
                # is only a safety net.
                placement_problem = t(language, "errors.placement_webhook")
                await show(interaction, SendConfirmView(session, error=placement_problem))
                return

            unsendable = sendable_problem(language, placed, session.library)
            if unsendable is not None:
                await show(interaction, SendConfirmView(session, error=unsendable))
                return

            if total_text_length(nodes) > MAX_V2_TOTAL_TEXT_LENGTH:
                # The editor keeps every text within the limit, so only a stored template could get here with too much.
                text_problem = t(language, "errors.total_text", max=MAX_V2_TOTAL_TEXT_LENGTH)
                await show(interaction, SendConfirmView(session, error=text_problem))
                return

            allowed = build_allowed_mentions(channel, member)
            persisted = await persist_items(
                session.library, placed, guild_id=session.guild_id, creator_id=session.slashcmd_author_id
            )

            sent: Message | WebhookMessage
            try:
                if session.webhook.enabled:
                    via_webhook, webhook_error = await send_via_webhook(interaction, channel, session, nodes, allowed)
                    if via_webhook is None:
                        await rollback(session.library, persisted)
                        await show(interaction, SendConfirmView(session, error=webhook_error))
                        return
                    sent = via_webhook
                else:
                    assert isinstance(channel, Messageable)
                    sent = await channel.send(view=StaticLayoutView(final_items(session, nodes)), allowed_mentions=allowed)

            except HTTPException as failure:
                await rollback(session.library, persisted)
                problem = send_problem_text(session.language, failure)
                if problem is None:
                    raise
                await show(interaction, SendConfirmView(session, error=problem))
                return

            except BaseException:
                await rollback(session.library, persisted)
                raise

            else:
                await attach(session.library, persisted, channel_id=sent.channel.id, message_id=sent.id)

                self.stop()
                success_text = (
                    f"{ts(session.language, 'info.success.sent')}\n\n{_jump_link_text(session.language, sent.jump_url)}"
                )
                success_view = text_message_view(success_text, colour=Colour.green())
                await interaction.response.edit_message(view=success_view)

        async def on_cancel(interaction: Interaction) -> None:
            """Go back to the main screen without sending."""
            await show(interaction, MainView(session))

        add_button(
            nav_row, on_confirm, label=ts(session.language, "buttons.confirm_yes"), style=ButtonStyle.green, emoji="✅"
        )
        add_button(nav_row, on_cancel, label=ts(session.language, "buttons.confirm_no"), style=ButtonStyle.gray, emoji="✏️")
        self.add_item(nav_row)

        if error:
            self.add_error(error)


def _placed_drafts(session: ContainerBuilderSession, nodes: list[ComponentNode]) -> list[ItemDraft]:
    """The buttons that sit in `nodes`, in the order they appear in the message."""
    drafts = (session.library.get(item_id) for item_id in placed_item_ids(nodes))
    return [draft for draft in drafts if draft is not None]


def _jump_link_text(language: SupportedLanguage, jump_url: str) -> str:
    """Localized text linking to the sent message."""
    return ts(language, "info.success.jump_link", jump_url=jump_url)


async def save_message_changes(interaction: Interaction, session: ContainerBuilderSession, view: BuilderLayoutView) -> None:
    """Write the builder's current state back into the bot's own message that is being edited."""
    from features.misc.builder.container.views.gui import MainView

    assert session.target_message is not None
    message = session.target_message
    channel = message.channel
    assert isinstance(channel, GuildChannel | Thread)

    nodes: list[ComponentNode] = non_empty_nodes(session.components)
    if not nodes:
        error = t(session.language, "errors.nothing_to_save")
        await show(interaction, MainView(session, error=error))
        return

    missing: list[str] = missing_send_permissions(channel, channel.guild.me)
    if missing:
        channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
        permissions = format_missing_permissions(session.language, missing)
        error = ts(session.language, "errors.bot_permission_missing", channel=channel_ref, permissions=permissions)
        await show(interaction, MainView(session, error=error))
        return

    placed: list[ItemDraft] = _placed_drafts(session, nodes)
    unsendable: str | None = sendable_problem(session.language, placed, session.library)
    if unsendable is not None:
        await show(interaction, MainView(session, error=unsendable))
        return

    if total_text_length(nodes) > MAX_V2_TOTAL_TEXT_LENGTH:
        error = t(session.language, "errors.total_text", max=MAX_V2_TOTAL_TEXT_LENGTH)
        await show(interaction, MainView(session, error=error))
        return

    assert isinstance(interaction.user, Member)
    allowed: AllowedMentions = build_allowed_mentions(channel, interaction.user)
    persisted: Persisted = await persist_items(
        session.library,
        placed,
        guild_id=session.guild_id,
        creator_id=session.slashcmd_author_id,
    )
    try:
        await message.edit(view=StaticLayoutView(final_items(session, nodes)), allowed_mentions=allowed)
    except NotFound:
        # The message was deleted meanwhile: drop edit mode so the builder works as a fresh
        # "send a new message" session again (send button, webhook, channel), keeping all content.
        await rollback(session.library, persisted)
        for draft in session.library.items.values():
            draft.db_id = None

        session.library.loaded_db_ids.clear()
        session.edit_mode = False
        session.target_message = None
        error = ts(session.language, "errors.message_deleted")
        await show(interaction, MainView(session, error=error))
        return
    except HTTPException as error:
        await rollback(session.library, persisted)
        problem = send_problem_text(session.language, error)
        if problem is None:
            raise
        await show(interaction, MainView(session, error=problem))
        return
    except BaseException:
        await rollback(session.library, persisted)
        raise

    await attach(session.library, persisted, channel_id=channel.id, message_id=message.id)

    view.stop()
    saved_text = f"{ts(session.language, 'info.success.saved')}\n\n{_jump_link_text(session.language, message.jump_url)}"
    success_view = text_message_view(saved_text, colour=Colour.green())
    await interaction.response.edit_message(view=success_view)
