import contextlib

from discord import ButtonStyle, Colour, Forbidden, HTTPException, Interaction, NotFound, Webhook
from discord.ui import ActionRow, Container, TextDisplay

from features.misc.builder.container.modals.webhook import WebhookModal
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.container.util.placement import remove_interactive_items
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, info_container, show
from features.misc.builder.interactive.messages import screen
from features.misc.builder.session import WebhookSender


async def apply_sender(interaction: Interaction, session: ContainerBuilderSession, sender: WebhookSender) -> None:
    """Make `sender` the message's sender identity - after the user confirmed that the buttons that run actions
    are removed, if there are any (a webhook can only carry link buttons)."""
    if sender.enabled and session.library.interactive():
        await show(interaction, WebhookConfirmView(session, sender))
        return

    session.webhook = sender
    await show(interaction, WebhookView(session))


class WebhookConfirmView(BuilderLayoutView):
    """Warns that a webhook sender costs the buttons that run actions, and asks to confirm."""

    def __init__(self, session: ContainerBuilderSession, pending: WebhookSender) -> None:
        """`pending` is the sender identity that is only applied once the user confirms."""
        super().__init__()
        self.session = session
        language = session.language

        count = len(session.library.interactive())
        header = f"### ⚠️ ~ {screen(language, 'webhook_confirm.title')}"
        description = screen(language, "webhook_confirm.description", count=count)
        self.add_item(Container(TextDisplay(f"{header}\n{description}"), accent_colour=Colour.orange()))

        nav_row: ActionRow = ActionRow()

        async def on_confirm(interaction: Interaction) -> None:
            """Remove the buttons that run actions and apply the sender identity."""
            remove_interactive_items(session)
            session.webhook = pending
            await show(interaction, WebhookView(session))

        async def on_cancel(interaction: Interaction) -> None:
            """Keep everything as it was and go back to the webhook screen."""
            await show(interaction, WebhookView(session))

        add_button(nav_row, on_confirm, label=ts(language, "buttons.confirm_yes"), style=ButtonStyle.red, emoji="✅")
        add_button(nav_row, on_cancel, label=ts(language, "buttons.confirm_no"), style=ButtonStyle.gray, emoji="✏️")
        self.add_item(nav_row)


class WebhookView(BuilderLayoutView):
    """Lets the user pick a custom sender identity (name/avatar/webhook) for the message."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error box to show."""
        from features.misc.builder.container.views.gui import MainView

        super().__init__()
        self.session = session

        webhook = session.webhook
        if webhook.enabled:
            username = webhook.username or webhook.display_name or "—"
            status_line = ts(session.language, "info.webhook.enabled", username=username)
        else:
            bot_name = session.slashcmd_channel.guild.me.display_name
            status_line = ts(session.language, "info.webhook.disabled", username=bot_name)

        description = ts(session.language, "info.webhook.description")
        title = ts(session.language, "info.webhook.title")
        self.add_item(info_container(f"### {title}\n{description}\n\n{status_line}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the main screen."""
            await show(interaction, MainView(session))

        async def on_set(interaction: Interaction) -> None:
            """Open the modal to set the custom sender name and avatar."""
            await interaction.response.send_modal(WebhookModal(session))

        async def on_remove(interaction: Interaction) -> None:
            """Delete the webhook, if any, and reset the sender to the bot."""
            if session.webhook.webhook_url:
                with contextlib.suppress(NotFound, Forbidden, HTTPException):
                    await Webhook.from_url(session.webhook.webhook_url, client=interaction.client).delete()

            session.webhook = WebhookSender()
            await show(interaction, WebhookView(session))

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        set_label = ts(session.language, "buttons.webhook_edit" if webhook.enabled else "buttons.webhook_set")
        add_button(nav_row, on_set, label=set_label, style=ButtonStyle.blurple, emoji="✏️" if webhook.enabled else "➕")
        add_button(
            nav_row,
            on_remove,
            label=ts(session.language, "buttons.webhook_remove"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=not webhook.enabled,
        )
        self.add_item(nav_row)

        if error:
            self.add_error(error)
