from discord import (
    Interaction,
)
from discord.ui import ChannelSelect, Label, Modal, TextInput

from core.discord_api.limits import MAX_EMBED_URL, MAX_WEBHOOK_AVATARURL, MAX_WEBHOOK_USERNAME
from core.i18n.translator import translate
from features.misc.builder.channels import TARGET_CHANNEL_TYPES, resolve_selected_channel
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.validation import append_error
from features.misc.builder.validation import is_valid_image_url
from features.misc.builder.webhook import resolve_new_sender


class WebhookModal(Modal):
    """Modal to set the custom sender name and avatar used when sending through a webhook."""

    def __init__(self, session: BuilderSession) -> None:
        """Pre-fill the fields with the sender identity currently set on the session."""
        super().__init__(title=translate(session.language, "builder.modals.webhook.title"))
        self.session: BuilderSession = session

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.webhook.name.question"),
            placeholder=translate(session.language, "builder.modals.webhook.name.placeholder"),
            required=False,
            max_length=MAX_WEBHOOK_USERNAME,
            default=session.webhook.username,
        )

        self.avatar_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.webhook.avatar.question"),
            placeholder=translate(session.language, "builder.modals.webhook.avatar.placeholder"),
            required=False,
            max_length=MAX_WEBHOOK_AVATARURL,
            default=session.webhook.avatar_url,
        )

        self.url_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.webhook.url.question"),
            placeholder=translate(session.language, "builder.modals.webhook.url.placeholder"),
            required=False,
            max_length=MAX_EMBED_URL,
            default=session.webhook.webhook_url if session.webhook.explicit_url else None,
        )

        self.add_item(self.name_input)
        self.add_item(self.avatar_input)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the avatar URL, store the sender identity on the session and show the webhook screen."""
        from features.misc.builder.embed.views.webhook import apply_sender

        session = self.session

        avatar_url: str = self.avatar_input.value.strip()
        if avatar_url and not is_valid_image_url(avatar_url):
            await self._reject(interaction, translate(session.language, "builder.errors.invalid_image"))
            return

        sender, error = await resolve_new_sender(
            interaction.client,
            session,
            username=self.name_input.value.strip() or None,
            avatar_url=avatar_url or None,
            webhook_url=self.url_input.value.strip(),
        )
        if sender is None:
            await self._reject(interaction, error or "")
            return
        await apply_sender(interaction, session, sender)

    async def _reject(self, interaction: Interaction, error: str) -> None:
        """Show the webhook screen again with `error` below it - nothing of what was typed is applied."""
        from features.misc.builder.embed.views import WebhookView

        view = WebhookView(self.session)
        await append_error(interaction, [view.info_embed], view, error)


class ChannelModal(Modal):
    """Modal to choose the channel the message is sent to."""

    def __init__(self, session: BuilderSession) -> None:
        """Offer the channel types a message can be sent to."""
        super().__init__(title=translate(session.language, "builder.modals.channel.title"))
        self.session: BuilderSession = session

        self.channel_input: ChannelSelect = ChannelSelect(
            required=False,
            placeholder=translate(session.language, "builder.modals.channel.placeholder"),
            channel_types=TARGET_CHANNEL_TYPES,
        )
        self.add_item(Label(text=translate(session.language, "builder.modals.channel.select"), component=self.channel_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Store the chosen channel - or reset to the default if none was chosen - and return to the main screen."""
        from features.misc.builder.embed.views import EmbedBuilderGUI, show

        if not self.channel_input.values:
            self.session.channel = None

        else:
            self.session.channel = await resolve_selected_channel(self.channel_input.values[0])

        await show(interaction, EmbedBuilderGUI(self.session))
