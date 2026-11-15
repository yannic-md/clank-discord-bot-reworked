from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from core.db.base import async_session
from core.db.models.interactive_builder.interactive_item import InteractiveItem, InteractiveItemUse


@dataclass(frozen=True, slots=True)
class InteractiveItemRecord:
    """A stored item, decoupled from the ORM model and from discord.py.

    `config_data` is the raw JSON payload; converting it to/from the interactive builder's
    data model is the feature layer's job.
    """

    id: int
    guild_id: int
    creator_id: int
    channel_id: int | None
    message_id: int | None
    kind: str
    config_data: dict[str, object]


def _to_record(row: InteractiveItem) -> InteractiveItemRecord:
    """Convert a database row into a record; a malformed `config` column counts as empty."""
    # `config` is a JSON column: a hand-edited or corrupted row could hold something other
    # than the expected object. Anything that is not a dict is treated as "empty config".
    stored: object = row.config
    return InteractiveItemRecord(
        id=row.id,
        guild_id=row.guild_id,
        creator_id=row.creator_id,
        channel_id=row.channel_id,
        message_id=row.message_id,
        kind=row.kind,
        config_data=dict(stored) if isinstance(stored, dict) else {},
    )


async def create_item(
    guild_id: int, creator_id: int, kind: str, config_data: dict[str, object], channel_id: int | None = None
) -> int:
    """Insert a new item that is not attached to a message yet and return its id."""
    async with async_session() as session:
        row = InteractiveItem(guild_id=guild_id, creator_id=creator_id, channel_id=channel_id, kind=kind, config=config_data)
        session.add(row)
        await session.commit()
        return row.id


async def get_item(item_id: int) -> InteractiveItemRecord | None:
    """The item with this id, or `None` if it does not exist (any more)."""
    async with async_session() as session:
        row = await session.get(InteractiveItem, item_id)
        return _to_record(row) if row is not None else None


async def list_items_for_message(message_id: int) -> list[InteractiveItemRecord]:
    """Every item attached to a message, ordered by id."""
    async with async_session() as session:
        rows = await session.scalars(
            select(InteractiveItem).where(InteractiveItem.message_id == message_id).order_by(InteractiveItem.id)
        )
        return [_to_record(row) for row in rows]


async def update_item_config(item_id: int, config_data: dict[str, object]) -> None:
    """Replace the config of an item; a no-op if it does not exist."""
    async with async_session() as session:
        await session.execute(update(InteractiveItem).where(InteractiveItem.id == item_id).values(config=config_data))
        await session.commit()


async def attach_items_to_message(item_ids: Collection[int], channel_id: int, message_id: int) -> None:
    """Record which message the items ended up on, once it has been sent."""
    if not item_ids:
        return

    async with async_session() as session:
        await session.execute(
            update(InteractiveItem)
            .where(InteractiveItem.id.in_(item_ids))
            .values(channel_id=channel_id, message_id=message_id)
        )
        await session.commit()


async def delete_items(item_ids: Collection[int]) -> None:
    """Remove items by id (their recorded uses go with them); ids that do not exist are ignored."""
    if not item_ids:
        return

    async with async_session() as session:
        await session.execute(delete(InteractiveItem).where(InteractiveItem.id.in_(item_ids)))
        await session.commit()


async def delete_items_for_messages(message_ids: Collection[int]) -> None:
    """Remove every item attached to any of these messages."""
    if not message_ids:
        return

    async with async_session() as session:
        await session.execute(delete(InteractiveItem).where(InteractiveItem.message_id.in_(message_ids)))
        await session.commit()


async def delete_items_for_channel(channel_id: int) -> None:
    """Remove every item attached to messages of this channel (or thread)."""
    async with async_session() as session:
        await session.execute(delete(InteractiveItem).where(InteractiveItem.channel_id == channel_id))
        await session.commit()


async def delete_items_for_guild(guild_id: int) -> None:
    """Remove every item of a guild, e.g. after the bot was removed from it."""
    async with async_session() as session:
        await session.execute(delete(InteractiveItem).where(InteractiveItem.guild_id == guild_id))
        await session.commit()


async def reserve_use(item_id: int, option_key: str, user_id: int) -> bool:
    """Atomically record that the user uses the item (option) for the first time.

    Returns:
        bool: `True` if this call recorded the use, `False` if the user had already used it.
    """
    async with async_session() as session:
        stmt = (
            mysql_insert(InteractiveItemUse)
            .values(item_id=item_id, option_key=option_key, user_id=user_id)
            .prefix_with("IGNORE")
        )
        result = await session.execute(stmt)
        await session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def has_used(item_id: int, option_key: str, user_id: int) -> bool:
    """Whether the user has already used the item (option) - without counting a use."""
    async with async_session() as session:
        found = await session.scalar(
            select(InteractiveItemUse.user_id).where(
                InteractiveItemUse.item_id == item_id,
                InteractiveItemUse.option_key == option_key,
                InteractiveItemUse.user_id == user_id,
            )
        )
        return found is not None


async def release_use(item_id: int, option_key: str, user_id: int) -> None:
    """Undo a `reserve_use`, e.g. because the actions behind it failed."""
    async with async_session() as session:
        await session.execute(
            delete(InteractiveItemUse).where(
                InteractiveItemUse.item_id == item_id,
                InteractiveItemUse.option_key == option_key,
                InteractiveItemUse.user_id == user_id,
            )
        )
        await session.commit()


async def reset_uses(item_id: int) -> None:
    """Forget who has already used an item, so everyone may use it once more."""
    async with async_session() as session:
        await session.execute(delete(InteractiveItemUse).where(InteractiveItemUse.item_id == item_id))
        await session.commit()
