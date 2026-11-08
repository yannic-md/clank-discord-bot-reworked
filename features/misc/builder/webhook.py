from typing import Any

from discord import Client, ClientUser, ForumChannel, StageChannel, TextChannel, Thread, VoiceChannel, Webhook
from discord.abc import GuildChannel
from discord.utils import MISSING

from features.misc.builder.session import WebhookSender

WEBHOOK_LIMIT_ERROR_CODE: int = 30007  # too much webhooks (from discord docs)


async def find_webhook(channel: GuildChannel | Thread, webhook_name: str | None, bot_user: ClientUser | None) -> Webhook:
    """Find a reusable webhook in `channel` (matching `webhook_name`, else bot-owned) or create one.

    Raises:
        Forbidden: The bot lacks `manage_webhooks` in the channel.
        HTTPException: Creating the webhook failed (e.g. the channel's 15-webhook limit was reached).
        ValueError: `channel` (or a thread's parent channel) doesn't support webhooks.
    """
    target: GuildChannel | None = channel.parent if isinstance(channel, Thread) else channel
    if not isinstance(target, (TextChannel, VoiceChannel, StageChannel, ForumChannel)):
        raise ValueError(f"Channel of type {type(channel).__name__} does not support webhooks.")

    existing_webhooks: list[Webhook] = await target.webhooks()
    match: Webhook | None = None
    if webhook_name:
        match = next((webhook for webhook in existing_webhooks if webhook.name == webhook_name), None)

    if match is None and bot_user is not None:
        match = next(
            (webhook for webhook in existing_webhooks if webhook.user is not None and webhook.user.id == bot_user.id), None
        )

    if match is not None:
        return match

    name: str = webhook_name or (bot_user.name if bot_user is not None else "Embed Builder")
    return await target.create_webhook(name=name)


async def resolve_send_webhook(client: Client, channel: GuildChannel | Thread, sender: WebhookSender) -> Webhook:
    """The webhook to send a message through, for `sender`'s identity.

    An explicitly pasted webhook URL is always reused as-is; an auto-resolved one is only trusted
    for the channel it was validated for, and re-resolved (found or created) otherwise.

    Raises:
        Forbidden: The bot lacks `manage_webhooks` in the channel.
        HTTPException: Creating the webhook failed (`WEBHOOK_LIMIT_ERROR_CODE` if the channel is full).
    """
    if sender.webhook_url is not None and (sender.explicit_url or sender.validated_channel_id == channel.id):
        return Webhook.from_url(sender.webhook_url, client=client)

    return await find_webhook(channel, sender.username, client.user)


def identity_kwargs(sender: WebhookSender, channel: GuildChannel | Thread) -> dict[str, Any]:
    """`Webhook.send` arguments for `sender`'s identity and the target `channel`.

    Only overrides the webhook's own name/avatar if the user explicitly set one - a webhook reused
    via URL (or by name) otherwise keeps its own configured identity. MISSING (discord.py's "not
    provided" sentinel) is passed for anything unset.
    """
    return {
        "username": sender.username or MISSING,
        "avatar_url": sender.avatar_url or MISSING,
        "thread": channel if isinstance(channel, Thread) else MISSING,
    }
