from discord import ChannelType, Thread
from discord.abc import GuildChannel
from discord.app_commands import AppCommandChannel, AppCommandThread

TARGET_CHANNEL_TYPES: list[ChannelType] = [
    ChannelType.text,
    ChannelType.news,
    ChannelType.public_thread,
    ChannelType.private_thread,
    ChannelType.voice,
    ChannelType.stage_voice,
]
"""The channel types a message can be sent to (offered in the "channel" modal of both builders)."""


async def resolve_selected_channel(selected: AppCommandChannel | AppCommandThread) -> GuildChannel | Thread:
    """Turn a `ChannelSelect` value into the real channel object.

    `ChannelSelect.values` returns lightweight `AppCommandChannel`/`AppCommandThread`
    wrappers, not real channel objects - resolve to the real (cached, or fetched)
    channel so later code (e.g. `permissions_for`) works on it.
    """
    return selected.resolve() or await selected.fetch()
