from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert

from core.db.base import async_session
from core.db.models.embed_builder.embed_template import EmbedTemplate


@dataclass(frozen=True, slots=True)
class EmbedTemplateRecord:
    """A stored embed template, decoupled from the ORM model and from discord.py.

    `embeds_data` is the raw JSON payload (a list of `discord.Embed.to_dict()`
    dicts); converting it to/from `discord.Embed` is the feature layer's job.
    """

    name: str
    icon: str
    content: str
    embeds_data: list[dict[str, object]]


def _to_record(row: EmbedTemplate) -> EmbedTemplateRecord:
    # `embeds` is a JSON column: a hand-edited or corrupted row could hold something
    # other than the expected array of embed dicts. Anything that is not a list is
    # treated as "no embeds" rather than propagated as a type error downstream.
    stored: object = row.embeds
    return EmbedTemplateRecord(
        name=row.name,
        icon=row.icon,
        content=row.message_content,
        embeds_data=list(stored) if isinstance(stored, list) else [],
    )


async def list_user_templates(user_id: int) -> list[EmbedTemplateRecord]:
    """Every template owned by a user, ordered by name.

    Returns the full rows (embed payload included): a user has at most a handful
    of small templates, so one query here powers both the picker and the restore
    of whichever template is then selected, with no follow-up lookup.
    """
    async with async_session() as session:
        rows = await session.scalars(
            select(EmbedTemplate).where(EmbedTemplate.user_id == user_id).order_by(EmbedTemplate.name)
        )
        return [_to_record(row) for row in rows]


async def upsert_user_template(
    user_id: int,
    name: str,
    icon: str,
    content: str,
    embeds_data: list[dict[str, object]],
) -> None:
    """Create the template, or replace the user's existing one with the same name.

    On replace, `created_at` is left as it was - only the payload and `updated_at`
    change.
    """
    async with async_session() as session:
        stmt: MySQLInsert = mysql_insert(EmbedTemplate).values(
            user_id=user_id,
            name=name,
            icon=icon,
            message_content=content,
            embeds=embeds_data,
        )

        stmt = stmt.on_duplicate_key_update(
            icon=stmt.inserted.icon,
            message_content=stmt.inserted.message_content,
            embeds=stmt.inserted.embeds,
            updated_at=func.now(),
        )

        await session.execute(stmt)
        await session.commit()


async def delete_user_template(user_id: int, name: str) -> None:
    """Remove a template by `(user_id, name)`; a no-op if it does not exist."""
    async with async_session() as session:
        await session.execute(delete(EmbedTemplate).where(EmbedTemplate.user_id == user_id, EmbedTemplate.name == name))
        await session.commit()
