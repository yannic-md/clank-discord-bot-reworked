from discord import AllowedMentions, Forbidden, HTTPException, Interaction, NotFound, Thread, WebhookMessage
from discord.abc import GuildChannel

from core.discord_api.limits import MAX_WEBHOOK_COUNT
from core.enums.language import SupportedLanguage
from features.misc.builder.container.models import ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import ts
from features.misc.builder.container.util.render import StaticLayoutView, build_items
from features.misc.builder.session import WebhookSender
from features.misc.builder.validation import get_channel_placeholder
from features.misc.builder.webhook import WEBHOOK_LIMIT_ERROR_CODE, identity_kwargs, resolve_send_webhook


async def send_via_webhook(
    interaction: Interaction,
    channel: GuildChannel | Thread,
    session: ContainerBuilderSession,
    nodes: list[ComponentNode],
    allowed: AllowedMentions,
) -> tuple[WebhookMessage | None, str | None]:
    """Send the message via the session's webhook identity.

    Returns `(message, None)` on success, or `(None, error_text)` if the bot lacks
    `manage_webhooks`, the channel's webhook limit is reached, or the cached webhook was
    deleted since it was last validated.
    """
    try:
        webhook = await resolve_send_webhook(interaction.client, channel, session.webhook)
    except Forbidden:
        return None, webhook_forbidden_text(session, channel)
    except HTTPException as error:
        if error.code != WEBHOOK_LIMIT_ERROR_CODE:
            raise
        return None, webhook_limit_text(session, channel)

    try:
        message = await webhook.send(
            view=StaticLayoutView(build_items(nodes)),
            allowed_mentions=allowed,
            wait=True,
            **identity_kwargs(session.webhook, channel),
        )
    except NotFound:
        # The webhook is gone - stop treating it as a configured identity going forward.
        session.webhook = WebhookSender()
        return None, webhook_invalid_text(session.language)
    return message, None


def webhook_forbidden_text(session: ContainerBuilderSession, channel: GuildChannel | Thread) -> str:
    """Error text for missing permission to manage webhooks in `channel`."""
    channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
    return ts(session.language, "errors.webhook_forbidden", channel=channel_ref)


def webhook_limit_text(session: ContainerBuilderSession, channel: GuildChannel | Thread) -> str:
    """Error text for `channel` having reached Discord's webhook limit."""
    channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
    return ts(session.language, "errors.webhook_limit", channel=channel_ref, limit=MAX_WEBHOOK_COUNT)


def webhook_invalid_text(language: SupportedLanguage) -> str:
    """Error text for a webhook that is no longer valid."""
    return ts(language, "errors.webhook_invalid")
