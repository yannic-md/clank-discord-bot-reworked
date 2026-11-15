from discord import Interaction
from discord.ui import ChannelSelect, Label, Modal, TextInput

from core.discord_api.limits import MAX_EMBED_URL, MAX_WEBHOOK_AVATARURL, MAX_WEBHOOK_USERNAME
from features.misc.builder.channels import TARGET_CHANNEL_TYPES, resolve_selected_channel
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.validation import is_valid_image_url
from features.misc.builder.webhook import resolve_new_sender


class WebhookModal(Modal):
    """Modal to set the custom sender name and avatar used when sending through a webhook."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        """Pre-fill the fields with the sender identity currently set on the session."""
        super().__init__(title=ts(session.language, "modals.webhook.title"))
        self.session = session

        self.name_input: TextInput = TextInput(
            label=ts(session.language, "modals.webhook.name.question"),
            placeholder=ts(session.language, "modals.webhook.name.placeholder"),
            required=False,
            max_length=MAX_WEBHOOK_USERNAME,
            default=session.webhook.username,
        )
        self.avatar_input: TextInput = TextInput(
            label=ts(session.language, "modals.webhook.avatar.question"),
            placeholder=ts(session.language, "modals.webhook.avatar.placeholder"),
            required=False,
            max_length=MAX_WEBHOOK_AVATARURL,
            default=session.webhook.avatar_url,
        )
        self.url_input: TextInput = TextInput(
            label=ts(session.language, "modals.webhook.url.question"),
            placeholder=ts(session.language, "modals.webhook.url.placeholder"),
            required=False,
            max_length=MAX_EMBED_URL,
            default=session.webhook.webhook_url if session.webhook.explicit_url else None,
        )
        self.add_item(self.name_input)
        self.add_item(self.avatar_input)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the avatar URL, store the sender identity on the session and show the webhook screen."""
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.webhook import WebhookView, apply_sender

        session = self.session

        avatar_url = self.avatar_input.value.strip()
        if avatar_url and not is_valid_image_url(avatar_url):
            await show(interaction, WebhookView(session, error=ts(session.language, "errors.invalid_image")))
            return

        sender, error = await resolve_new_sender(
            interaction.client,
            session,
            username=self.name_input.value.strip() or None,
            avatar_url=avatar_url or None,
            webhook_url=self.url_input.value.strip(),
        )
        if sender is None:
            await show(interaction, WebhookView(session, error=error))
            return
        await apply_sender(interaction, session, sender)


class ChannelModal(Modal):
    """Modal to choose the channel the message is sent to."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        """Offer the channel types a message can be sent to."""
        super().__init__(title=ts(session.language, "modals.channel.title"))
        self.session = session

        self.channel_input: ChannelSelect = ChannelSelect(
            required=False,
            placeholder=ts(session.language, "modals.channel.placeholder"),
            channel_types=TARGET_CHANNEL_TYPES,
        )
        self.add_item(Label(text=ts(session.language, "modals.channel.select"), component=self.channel_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Store the chosen channel - or reset to the default if none was chosen - and show the main screen."""
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.gui import MainView

        if not self.channel_input.values:
            self.session.channel = None
        else:
            self.session.channel = await resolve_selected_channel(self.channel_input.values[0])

        await show(interaction, MainView(self.session))
