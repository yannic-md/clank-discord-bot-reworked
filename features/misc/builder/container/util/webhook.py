from discord import AllowedMentions, Forbidden, HTTPException, Interaction, Thread, WebhookMessage
from discord.abc import GuildChannel

from features.misc.builder.container.models import ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.util.render import StaticLayoutView, final_items
from features.misc.builder.session import WebhookSender
from features.misc.builder.webhook import (
    WEBHOOK_LIMIT_ERROR_CODE,
    identity_kwargs,
    resolve_send_webhook,
    webhook_forbidden_text,
    webhook_invalid_text,
    webhook_limit_text,
)


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
            view=StaticLayoutView(final_items(session, nodes)),
            allowed_mentions=allowed,
            wait=True,
            **identity_kwargs(session.webhook, channel),
        )
    except HTTPException as error:
        if error.status not in (401, 404):  # 404: the webhook is gone; 401: its token is wrong
            raise

        # The webhook cannot be used - stop treating it as a configured identity going forward.
        session.webhook = WebhookSender()
        return None, webhook_invalid_text(session.language)
    return message, None
