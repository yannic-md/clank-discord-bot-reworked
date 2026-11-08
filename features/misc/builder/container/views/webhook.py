import contextlib

from discord import ButtonStyle, Forbidden, HTTPException, Interaction, NotFound, Webhook
from discord.ui import ActionRow

from features.misc.builder.container.modals.webhook import WebhookModal
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, info_container, show
from features.misc.builder.session import WebhookSender


class WebhookView(BuilderLayoutView):
    """Lets the user pick a custom sender identity (name/avatar/webhook) for the message."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
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
            await show(interaction, MainView(session))

        async def on_set(interaction: Interaction) -> None:
            await interaction.response.send_modal(WebhookModal(session))

        async def on_remove(interaction: Interaction) -> None:
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
