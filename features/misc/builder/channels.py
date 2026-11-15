from discord import ChannelType, ClientException, Forbidden, Guild, HTTPException, Member, NotFound, Thread
from discord.abc import GuildChannel
from discord.app_commands import AppCommandChannel, AppCommandThread

TARGET_CHANNEL_TYPES: list[ChannelType] = [
    ChannelType.text,
    ChannelType.news,
    ChannelType.public_thread,
    ChannelType.private_thread,
    ChannelType.news_thread,
    ChannelType.voice,
    ChannelType.stage_voice,
]
"""The channel types a message can be sent to."""


def can_post_in(channel: GuildChannel | Thread, member: Member) -> bool:
    """Whether `member` can see `channel` and write in it. A thread has its own permission for writing: a thread
    takes over the other permissions of its parent channel, but `send_messages` there says nothing about the thread."""
    try:
        permissions = channel.permissions_for(member)
    except ClientException:  # a thread whose parent channel is not known
        return False

    can_send: bool = permissions.send_messages_in_threads if isinstance(channel, Thread) else permissions.send_messages
    return permissions.view_channel and can_send


async def find_channel(guild: Guild, channel_id: int) -> GuildChannel | Thread | None:
    """The channel or thread of the guild with this id.
    A thread that was archived is no longer cached, so it is asked for."""
    cached = guild.get_channel_or_thread(channel_id)
    if cached is not None:
        return cached

    try:
        return await guild.fetch_channel(channel_id)
    except NotFound, Forbidden, HTTPException:
        return None


async def resolve_selected_channel(selected: AppCommandChannel | AppCommandThread) -> GuildChannel | Thread:
    """Turn a `ChannelSelect` value into the real channel object.

    `ChannelSelect.values` returns lightweight `AppCommandChannel`/`AppCommandThread`
    wrappers, not real channel objects - resolve to the real (cached, or fetched)
    channel so later code (e.g. `permissions_for`) works on it.
    """
    return selected.resolve() or await selected.fetch()
