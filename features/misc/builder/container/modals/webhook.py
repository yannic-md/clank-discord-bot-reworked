from discord import Forbidden, HTTPException, Interaction, NotFound, Webhook
from discord.ui import ChannelSelect, Label, Modal, TextInput

from core.discord_api.limits import MAX_EMBED_URL, MAX_WEBHOOK_AVATARURL, MAX_WEBHOOK_USERNAME
from features.misc.builder.channels import TARGET_CHANNEL_TYPES, resolve_selected_channel
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.container.util.webhook import webhook_forbidden_text, webhook_invalid_text, webhook_limit_text
from features.misc.builder.session import WebhookSender
from features.misc.builder.validation import is_valid_image_url
from features.misc.builder.webhook import WEBHOOK_LIMIT_ERROR_CODE, find_webhook


class WebhookModal(Modal):
    def __init__(self, session: ContainerBuilderSession) -> None:
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
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.webhook import WebhookView

        session = self.session

        avatar_url = self.avatar_input.value.strip()
        if avatar_url and not is_valid_image_url(avatar_url):
            error = ts(session.language, "errors.invalid_image")
            await show(interaction, WebhookView(session, error=error))
            return

        username = self.name_input.value.strip() or None
        webhook_url = self.url_input.value.strip()

        # An explicitly pasted webhook URL is used as-is instead of creating one for the current channel.
        if webhook_url:
            try:
                webhook = Webhook.from_url(webhook_url, client=interaction.client)
                webhook = await webhook.fetch()
            except ValueError, NotFound, Forbidden, HTTPException:
                await show(interaction, WebhookView(session, error=webhook_invalid_text(session.language)))
                return

            session.webhook = WebhookSender(
                username=username,
                avatar_url=avatar_url or None,
                webhook_url=webhook.url,
                validated_channel_id=webhook.channel_id,
                explicit_url=True,
                display_name=webhook.name,
            )
            await show(interaction, WebhookView(session))
            return

        channel = session.target_channel
        try:
            webhook = await find_webhook(channel, username, interaction.client.user)
        except Forbidden:
            await show(interaction, WebhookView(session, error=webhook_forbidden_text(session, channel)))
            return
        except HTTPException as error:
            if error.code == WEBHOOK_LIMIT_ERROR_CODE:
                await show(interaction, WebhookView(session, error=webhook_limit_text(session, channel)))
                return
            raise

        session.webhook = WebhookSender(
            username=username,
            avatar_url=avatar_url or None,
            webhook_url=webhook.url,
            validated_channel_id=channel.id,
            display_name=webhook.name,
        )
        await show(interaction, WebhookView(session))


class ChannelModal(Modal):
    def __init__(self, session: ContainerBuilderSession) -> None:
        super().__init__(title=ts(session.language, "modals.channel.title"))
        self.session = session

        self.channel_input: ChannelSelect = ChannelSelect(
            required=False,
            placeholder=ts(session.language, "modals.channel.placeholder"),
            channel_types=TARGET_CHANNEL_TYPES,
        )
        self.add_item(Label(text=ts(session.language, "modals.channel.select"), component=self.channel_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.gui import MainView

        if not self.channel_input.values:
            self.session.channel = None
        else:
            self.session.channel = await resolve_selected_channel(self.channel_input.values[0])

        await show(interaction, MainView(self.session))
