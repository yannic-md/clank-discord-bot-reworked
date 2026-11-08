from discord import (
    Forbidden,
    HTTPException,
    Interaction,
    NotFound,
    Thread,
    Webhook,
)
from discord.abc import GuildChannel
from discord.ui import ChannelSelect, Label, Modal, TextInput

from core.discord_api.limits import MAX_EMBED_URL, MAX_WEBHOOK_AVATARURL, MAX_WEBHOOK_COUNT, MAX_WEBHOOK_USERNAME
from core.i18n.translator import translate
from features.misc.builder.channels import TARGET_CHANNEL_TYPES, resolve_selected_channel
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.validation import append_error
from features.misc.builder.session import WebhookSender
from features.misc.builder.validation import get_channel_placeholder, is_valid_image_url
from features.misc.builder.webhook import WEBHOOK_LIMIT_ERROR_CODE, find_webhook


class WebhookModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
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
        from features.misc.builder.embed.views import WebhookView, show

        avatar_url: str = self.avatar_input.value.strip()
        if avatar_url and not is_valid_image_url(avatar_url):
            await append_error(
                interaction,
                [WebhookView(self.session).info_embed],
                WebhookView(self.session),
                translate(self.session.language, "builder.errors.invalid_image"),
            )
            return

        username: str | None = self.name_input.value.strip() or None
        webhook_url: str = self.url_input.value.strip()

        # An explicitly pasted webhook URL is used as-is instead of creating one for the current channel.
        if webhook_url:
            try:
                webhook: Webhook = Webhook.from_url(webhook_url, client=interaction.client)
                webhook = await webhook.fetch()
            except ValueError, NotFound, Forbidden, HTTPException:
                await append_error(
                    interaction,
                    [WebhookView(self.session).info_embed],
                    WebhookView(self.session),
                    translate(self.session.language, "builder.errors.webhook_invalid"),
                )
                return

            self.session.webhook = WebhookSender(
                username=username,
                avatar_url=avatar_url or None,
                webhook_url=webhook.url,
                validated_channel_id=webhook.channel_id,
                explicit_url=True,
                display_name=webhook.name,
            )
            await show(interaction, WebhookView(self.session))
            return

        channel: GuildChannel | Thread = self.session.target_channel
        channel_ref: str = get_channel_placeholder(self.session.language, channel, self.session.slashcmd_channel.id)

        try:
            webhook = await find_webhook(channel, username, interaction.client.user)
        except Forbidden:
            await append_error(
                interaction,
                [WebhookView(self.session).info_embed],
                WebhookView(self.session),
                translate(self.session.language, "builder.errors.webhook_forbidden", channel=channel_ref),
            )
            return

        except HTTPException as error:
            if error.code == WEBHOOK_LIMIT_ERROR_CODE:
                await append_error(
                    interaction,
                    [WebhookView(self.session).info_embed],
                    WebhookView(self.session),
                    translate(
                        self.session.language,
                        "builder.errors.webhook_limit",
                        channel=channel_ref,
                        limit=MAX_WEBHOOK_COUNT,
                    ),
                )
                return
            raise

        self.session.webhook = WebhookSender(
            username=username,
            avatar_url=avatar_url or None,
            webhook_url=webhook.url,
            validated_channel_id=channel.id,
            display_name=webhook.name,
        )

        await show(interaction, WebhookView(self.session))


class ChannelModal(Modal):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__(title=translate(session.language, "builder.modals.channel.title"))
        self.session: BuilderSession = session

        self.channel_input: ChannelSelect = ChannelSelect(
            required=False,
            placeholder=translate(session.language, "builder.modals.channel.placeholder"),
            channel_types=TARGET_CHANNEL_TYPES,
        )
        self.add_item(Label(text=translate(session.language, "builder.modals.channel.select"), component=self.channel_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.builder.embed.views import EmbedBuilderGUI, show

        if not self.channel_input.values:
            self.session.channel = None

        else:
            self.session.channel = await resolve_selected_channel(self.channel_input.values[0])

        await show(interaction, EmbedBuilderGUI(self.session))
