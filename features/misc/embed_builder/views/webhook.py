import contextlib

from discord import ButtonStyle, Colour, Embed, Forbidden, HTTPException, Interaction, NotFound, Webhook
from discord.ui import Button, button

from core.i18n.translator import translate
from features.misc.embed_builder.modals import WebhookModal
from features.misc.embed_builder.session import BuilderSession, WebhookSender
from features.misc.embed_builder.views.base import BuilderScreenView, show


class WebhookView(BuilderScreenView):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session

        if session.webhook.enabled:
            username: str = session.webhook.username or session.webhook.display_name or "—"
            status_line: str = translate(session.language, "builder.info.webhook.enabled", username=username)
        else:
            status_line = translate(session.language, "builder.info.webhook.disabled")

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.webhook.title"),
            description=f"{translate(session.language, 'builder.info.webhook.description')}\n\n{status_line}",
            colour=Colour.blurple(),
        )
        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]

        self.back_button.label = translate(session.language, "builder.buttons.back")
        self.back_button.emoji = "◀️"
        if session.webhook.enabled:
            self.set_button.label = translate(session.language, "builder.buttons.webhook_edit")
            self.set_button.emoji = "✏️"
        else:
            self.set_button.label = translate(session.language, "builder.buttons.webhook_set")
            self.set_button.emoji = "➕"

        self.remove_button.label = translate(session.language, "builder.buttons.webhook_remove")
        self.remove_button.emoji = "🗑️"
        self.remove_button.disabled = not session.webhook.enabled

    @button(label="Back", style=ButtonStyle.gray, row=0, custom_id="embed_builder:webhook:back")
    async def back_button(self: WebhookView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Set", style=ButtonStyle.blurple, row=0, custom_id="embed_builder:webhook:set")
    async def set_button(self: WebhookView, interaction: Interaction, _button: Button) -> None:
        await interaction.response.send_modal(WebhookModal(self.session))

    @button(label="Remove", style=ButtonStyle.red, row=0, custom_id="embed_builder:webhook:remove")
    async def remove_button(self: WebhookView, interaction: Interaction, _button: Button) -> None:
        if self.session.webhook.webhook_url:
            with contextlib.suppress(NotFound, Forbidden, HTTPException):
                await Webhook.from_url(self.session.webhook.webhook_url, client=interaction.client).delete()

        self.session.webhook = WebhookSender()
        await show(interaction, WebhookView(self.session))
