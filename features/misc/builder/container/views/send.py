from discord import ButtonStyle, Colour, Interaction, Member, Message, NotFound, Thread, WebhookMessage
from discord.abc import GuildChannel, Messageable
from discord.ui import ActionRow

from core.enums.language import SupportedLanguage
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.render import StaticLayoutView, build_items, text_message_view
from features.misc.builder.container.util.tree import non_empty_nodes
from features.misc.builder.container.util.webhook import send_via_webhook
from features.misc.builder.container.validation import contains_mass_mention, missing_send_permissions
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, info_container, show
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
        for item in build_items(nodes):
            self.add_item(item)

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
                error = ts(language, "errors.user_permission_missing", channel=channel_ref, permissions=permissions)
                await show(interaction, SendConfirmView(session, error=error))
                return

            missing = missing_send_permissions(channel, channel.guild.me)
            if missing:
                permissions = format_missing_permissions(language, missing)
                error = ts(language, "errors.bot_permission_missing", channel=channel_ref, permissions=permissions)
                await show(interaction, SendConfirmView(session, error=error))
                return

            allowed = build_allowed_mentions(channel, member)
            sent: Message | WebhookMessage | None
            if session.webhook.enabled:
                sent, webhook_error = await send_via_webhook(interaction, channel, session, nodes, allowed)
                if sent is None:
                    await show(interaction, SendConfirmView(session, error=webhook_error))
                    return
            else:
                assert isinstance(channel, Messageable)
                sent = await channel.send(view=StaticLayoutView(build_items(nodes)), allowed_mentions=allowed)

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

    nodes = non_empty_nodes(session.components)
    if not nodes:
        error = t(session.language, "errors.nothing_to_save")
        await show(interaction, MainView(session, error=error))
        return

    missing = missing_send_permissions(channel, channel.guild.me)
    if missing:
        channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
        permissions = format_missing_permissions(session.language, missing)
        error = ts(session.language, "errors.bot_permission_missing", channel=channel_ref, permissions=permissions)
        await show(interaction, MainView(session, error=error))
        return

    assert isinstance(interaction.user, Member)
    allowed = build_allowed_mentions(channel, interaction.user)
    try:
        await message.edit(view=StaticLayoutView(build_items(nodes)), allowed_mentions=allowed)
    except NotFound:
        # The message was deleted meanwhile: drop edit mode so the builder works as a fresh
        # "send a new message" session again (send button, webhook, channel), keeping all content.
        session.edit_mode = False
        session.target_message = None
        error = ts(session.language, "errors.message_deleted")
        await show(interaction, MainView(session, error=error))
        return

    view.stop()
    saved_text = f"{ts(session.language, 'info.success.saved')}\n\n{_jump_link_text(session.language, message.jump_url)}"
    success_view = text_message_view(saved_text, colour=Colour.green())
    await interaction.response.edit_message(view=success_view)
