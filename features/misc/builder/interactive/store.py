from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from core.db.repositories.interactive_builder.interactive_item_repository import (
    InteractiveItemRecord,
    attach_items_to_message,
    create_item,
    delete_items,
    update_item_config,
)
from features.misc.builder.interactive.draft import DraftKind, InteractiveLibrary, ItemDraft
from features.misc.builder.interactive.models import FormConfig, ItemConfig, ItemKind


@dataclass
class Persisted:
    """What `persist_items` stored: the ids of all interactive buttons of the message, and those that are new."""

    all_ids: list[int] = field(default_factory=list)
    new_ids: list[int] = field(default_factory=list)


async def persist_items(
    library: InteractiveLibrary, placed: Iterable[ItemDraft], *, guild_id: int, creator_id: int
) -> Persisted:
    """Store the interactive items of a message that is about to be sent or saved.

    New items get a row (and their `db_id`), items that already have one get their config updated. Link
    buttons need no row. The forms the items open are stored first, as the items refer to their rows. The rows are
    not attached to a message yet: that happens once the message exists (`attach`) - and if sending fails,
    `rollback` removes the new ones again.
    """
    drafts = list(placed)
    result = Persisted()
    form_ids: dict[int, int | None] = {}

    for form in library.referenced_forms(drafts):
        await _store(form, form_ids, result, guild_id=guild_id, creator_id=creator_id)
        form_ids[form.id] = form.db_id

    for draft in drafts:
        if not draft.is_link:
            await _store(draft, form_ids, result, guild_id=guild_id, creator_id=creator_id)
    return result


async def _store(
    draft: ItemDraft, form_ids: dict[int, int | None], result: Persisted, *, guild_id: int, creator_id: int
) -> None:
    """Create the row of an item, or update its config if it has one already."""
    data = draft.stored_config_data(form_ids)
    if draft.db_id is None:
        kind = ItemKind.FORM if draft.is_form else ItemKind.SELECT if draft.is_select else ItemKind.BUTTON
        draft.db_id = await create_item(guild_id, creator_id, kind.value, data)
        result.new_ids.append(draft.db_id)
    else:
        await update_item_config(draft.db_id, data)
    result.all_ids.append(draft.db_id)


async def rollback(library: InteractiveLibrary, persisted: Persisted) -> None:
    """Undo `persist_items` for the buttons it created, after the message could not be sent."""
    for draft in library.items.values():
        if draft.db_id in persisted.new_ids:
            draft.db_id = None
    await delete_items(persisted.new_ids)


async def attach(library: InteractiveLibrary, persisted: Persisted, *, channel_id: int, message_id: int) -> None:
    """Record which message the stored buttons sit on, and drop those that were on it before but are gone now."""
    await attach_items_to_message(persisted.all_ids, channel_id, message_id)

    removed = library.loaded_db_ids - set(persisted.all_ids)
    await delete_items(removed)
    library.loaded_db_ids = set(persisted.all_ids)


def draft_from_record(library: InteractiveLibrary, record: InteractiveItemRecord, **look: object) -> ItemDraft:
    """A draft for a stored button found on a message, taking over its stored behaviour.

    `look` is how the button appears on the message (`label`, `emoji`, `style`) - the row only
    stores what a click does, not how the button looks.
    """
    draft = library.new_draft(DraftKind.BUTTON, config=ItemConfig.from_data(record.config_data), db_id=record.id, **look)
    library.loaded_db_ids.add(record.id)
    return draft


def stored_ids(drafts: Collection[ItemDraft]) -> set[int]:
    """The database ids of the given drafts that have one."""
    return {draft.db_id for draft in drafts if draft.db_id is not None}


def form_draft_from_record(library: InteractiveLibrary, record: InteractiveItemRecord) -> ItemDraft:
    """A draft for a stored form found on a message, taking over its stored questions and behaviour."""
    stored = FormConfig.from_data(record.config_data)
    draft = library.new_draft(
        DraftKind.FORM,
        label=stored.title or None,
        questions=stored.questions,
        config=ItemConfig(actions=stored.actions, conditions=stored.conditions),
        db_id=record.id,
    )
    library.loaded_db_ids.add(record.id)
    return draft
