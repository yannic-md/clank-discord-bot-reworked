from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert

from core.db.base import async_session
from core.db.models.container_builder.container_template import ContainerTemplate


@dataclass(frozen=True, slots=True)
class ContainerTemplateRecord:
    """A stored container template, decoupled from the ORM model and from discord.py.

    `components_data` is the raw JSON payload (a list of plain component dicts);
    converting it to/from the builder's data model is the feature layer's job.
    """

    name: str
    icon: str
    components_data: list[dict[str, object]]


def _to_record(row: ContainerTemplate) -> ContainerTemplateRecord:
    """Convert a database row into a record; a malformed `components` column counts as empty."""
    # `components` is a JSON column: a hand-edited or corrupted row could hold something
    # other than the expected array. Anything that is not a list is treated as "no
    # components" rather than propagated as a type error downstream.
    stored: object = row.components
    return ContainerTemplateRecord(
        name=row.name,
        icon=row.icon,
        components_data=list(stored) if isinstance(stored, list) else [],
    )


async def list_user_templates(user_id: int) -> list[ContainerTemplateRecord]:
    """Every template owned by a user, ordered by name (full rows, payload included)."""
    async with async_session() as session:
        rows = await session.scalars(
            select(ContainerTemplate).where(ContainerTemplate.user_id == user_id).order_by(ContainerTemplate.name)
        )
        return [_to_record(row) for row in rows]


async def upsert_user_template(user_id: int, name: str, icon: str, components_data: list[dict[str, object]]) -> None:
    """Create the template, or replace the user's existing one with the same name.

    On replace, `created_at` is left as it was - only the payload and `updated_at` change.
    """
    async with async_session() as session:
        stmt: MySQLInsert = mysql_insert(ContainerTemplate).values(
            user_id=user_id,
            name=name,
            icon=icon,
            components=components_data,
        )

        stmt = stmt.on_duplicate_key_update(
            icon=stmt.inserted.icon,
            components=stmt.inserted.components,
            updated_at=func.now(),
        )

        await session.execute(stmt)
        await session.commit()


async def delete_user_template(user_id: int, name: str) -> None:
    """Remove a template by `(user_id, name)`; a no-op if it does not exist."""
    async with async_session() as session:
        await session.execute(
            delete(ContainerTemplate).where(ContainerTemplate.user_id == user_id, ContainerTemplate.name == name)
        )
        await session.commit()
