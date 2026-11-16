from typing import Any, Protocol

from discord import (
    Client,
    ClientUser,
    Forbidden,
    ForumChannel,
    HTTPException,
    NotFound,
    StageChannel,
    TextChannel,
    Thread,
    VoiceChannel,
    Webhook,
)
from discord.abc import GuildChannel
from discord.utils import MISSING

from core.discord_api.limits import MAX_WEBHOOK_COUNT
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.session import WebhookSender
from features.misc.builder.validation import get_channel_placeholder

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


class SenderSession(Protocol):
    """The part of a builder session the sender identity of a message is worked out from."""

    @property
    def language(self) -> SupportedLanguage:
        """The language the builder answers in."""
        ...

    @property
    def target_channel(self) -> GuildChannel | Thread:
        """The channel the message will be sent to."""
        ...

    @property
    def slashcmd_channel(self) -> GuildChannel | Thread:
        """The channel the builder was started in."""
        ...


def webhook_forbidden_text(session: SenderSession, channel: GuildChannel | Thread) -> str:
    """Error text for missing permission to manage webhooks in `channel`."""
    channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
    return translate(session.language, "builder.errors.webhook_forbidden", channel=channel_ref)


def webhook_limit_text(session: SenderSession, channel: GuildChannel | Thread) -> str:
    """Error text for `channel` having reached Discord's webhook limit."""
    channel_ref = get_channel_placeholder(session.language, channel, session.slashcmd_channel.id)
    return translate(session.language, "builder.errors.webhook_limit", channel=channel_ref, limit=MAX_WEBHOOK_COUNT)


def webhook_invalid_text(language: SupportedLanguage) -> str:
    """Error text for a webhook that is no longer valid."""
    return translate(language, "builder.errors.webhook_invalid")


async def resolve_new_sender(
    client: Client, session: SenderSession, *, username: str | None, avatar_url: str | None, webhook_url: str
) -> tuple[WebhookSender | None, str | None]:
    """The sender identity for what was typed into the webhook modal - or the text of the error that prevents one.

    A pasted `webhook_url` is checked and used as it is; without one, the webhook of the target channel is found or
    created. Returns `(sender, None)` on success and `(None, error_text)` if the webhook is not valid, the bot may not
    manage webhooks in the channel, or the channel has reached the webhook limit.

    Raises:
        HTTPException: Discord rejected the webhook for another reason.
    """
    if webhook_url:
        try:
            pasted = await Webhook.from_url(webhook_url, client=client).fetch()
        except ValueError, NotFound, Forbidden, HTTPException:
            return None, webhook_invalid_text(session.language)

        sender = WebhookSender(
            username=username,
            avatar_url=avatar_url,
            webhook_url=pasted.url,
            validated_channel_id=pasted.channel_id,
            explicit_url=True,
            display_name=pasted.name,
        )
        return sender, None

    channel = session.target_channel
    try:
        found = await find_webhook(channel, username, client.user)
    except Forbidden:
        return None, webhook_forbidden_text(session, channel)
    except HTTPException as error:
        if error.code == WEBHOOK_LIMIT_ERROR_CODE:
            return None, webhook_limit_text(session, channel)
        raise

    sender = WebhookSender(
        username=username,
        avatar_url=avatar_url,
        webhook_url=found.url,
        validated_channel_id=channel.id,
        display_name=found.name,
    )
    return sender, None
