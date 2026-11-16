import copy
from dataclasses import replace
from typing import Any

from discord import Message, SelectOption
from discord import components as api_components
from discord.ui import View

from core.db.repositories.interactive_builder.interactive_item_repository import InteractiveItemRecord
from core.i18n.translator import translate
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.interactive.draft import BUTTONS_PER_ROW, ItemDraft, adopt_forms, row_has_room, template_data
from features.misc.builder.interactive.imports import import_component
from features.misc.builder.interactive.render import final_component

MAX_ROWS: int = 5
PREVIEW_ROWS: int = 3
"""How many rows of the placed items the placement screen can show: the rest of its five rows hold its own controls."""
UNPLACE_VALUE: str = "unplace"
NEW_ROW_VALUE: str = "new_row"


def _t(session: BuilderSession, key: str, **variables: Any) -> str:
    """Translate a key of the `builder.embed` locale domain."""
    return translate(session.language, f"builder.embed.{key}", **variables)


def placed_item_ids(session: BuilderSession) -> list[int]:
    """The ids of all placed buttons, row by row."""
    return [item_id for row in session.button_rows for item_id in row]


def find_row(session: BuilderSession, item_id: int) -> int | None:
    """The index of the row holding the button, or `None` if it is not placed."""
    return next((index for index, row in enumerate(session.button_rows) if item_id in row), None)


def describe_placement(session: BuilderSession, item_id: int) -> str | None:
    """Localized name of the row the button sits in, or `None` if it is not placed."""
    index = find_row(session, item_id)
    return None if index is None else _t(session, "info.placement.row", row=index + 1)


def describe_layout(session: BuilderSession) -> str:
    """The rows as text lines, e.g. "Row 1: 🎮 Gamer · 📚 Docs" - the embed builder cannot preview buttons next to
    its own controls, so this is how the user sees what sits where."""
    from features.misc.builder.interactive.editor import draft_name

    if not session.button_rows:
        return _t(session, "info.placement.empty")

    lines: list[str] = []
    for index, row in enumerate(session.button_rows):
        names = [
            draft_name(session.language, draft) for item_id in row if (draft := session.library.get(item_id)) is not None
        ]
        lines.append(f"> {_t(session, 'info.placement.row', row=index + 1)}: {' · '.join(names)}")
    return "\n".join(lines)


def row_of(session: BuilderSession, item_id: int) -> list[int]:
    """The ids of the buttons in the row the button sits in, in order; empty if it is not placed."""
    index = find_row(session, item_id)
    return [] if index is None else session.button_rows[index]


def move_in_row(session: BuilderSession, item_id: int, offset: int) -> bool:
    """Move the button `offset` places along its row (`-1` to the left, `1` to the right). Returns whether it moved:
    a button that is not placed, or already at that end of its row, stays where it is."""
    row = row_of(session, item_id)
    if item_id not in row:
        return False

    position = row.index(item_id)
    target = position + offset
    if not 0 <= target < len(row):
        return False

    row[position], row[target] = row[target], row[position]
    return True


def unplace_item(session: BuilderSession, item_id: int) -> None:
    """Take the button out of the layout (it stays defined). Rows it leaves empty disappear."""
    for row in session.button_rows:
        if item_id in row:
            row.remove(item_id)
    session.button_rows[:] = [row for row in session.button_rows if row]


def delete_item(session: BuilderSession, item_id: int) -> None:
    """Delete the button altogether: out of the layout and out of the library."""
    unplace_item(session, item_id)
    session.library.remove(item_id)
    if session.active_item_id == item_id:
        session.active_item_id = None


def remove_interactive_items(session: BuilderSession) -> int:
    """Delete every button that runs actions (all but link buttons) and return how many there were."""
    interactive = session.library.interactive()
    for draft in interactive:
        delete_item(session, draft.id)
    return len(interactive)


def _drafts(session: BuilderSession, row: list[int]) -> list[ItemDraft]:
    """The items of a row, by id."""
    drafts = (session.library.get(item_id) for item_id in row)
    return [draft for draft in drafts if draft is not None]


def preview_rows(session: BuilderSession) -> list[list[ItemDraft]]:
    """The placed items row by row, as items; rows without one that still exists are left out."""
    rows = (_drafts(session, row) for row in session.button_rows)
    return [drafts for drafts in rows if drafts]


def _changes_layout(session: BuilderSession, draft: ItemDraft, target: str) -> bool:
    """Whether putting the button where `target` says changes the layout - or fails, which is worth telling. A button
    that is alone in the last row gains nothing from "a new row", and nothing from the row it is alone in."""
    probe = replace(session, button_rows=copy.deepcopy(session.button_rows))
    return place_item(probe, draft, target) is not None or probe.button_rows != session.button_rows


def placement_options(session: BuilderSession, draft: ItemDraft) -> list[SelectOption]:
    """Where the button can go: a new row (if there are fewer than five) or a row with room left. Where it would
    change nothing is not offered.

    The rows are numbered as the user sees them now. A row only the button itself occupies would disappear
    when it moves, which frees a row for a new one - that is taken into account.
    """
    if draft.is_form:
        return []
    current = find_row(session, draft.id)
    others = [[item_id for item_id in row if item_id != draft.id] for row in session.button_rows]
    remaining_rows = [row for row in others if row]

    options: list[SelectOption] = []
    if current is not None:
        options.append(SelectOption(label=_t(session, "select.placement.unplace"), value=UNPLACE_VALUE, emoji="🗑️"))

    places: list[SelectOption] = []
    if len(remaining_rows) < MAX_ROWS:
        places.append(SelectOption(label=_t(session, "select.placement.new_row"), value=NEW_ROW_VALUE, emoji="➕"))
    for index, row in enumerate(others):
        if row_has_room(_drafts(session, row), draft):
            label = _t(session, "info.placement.row", row=index + 1)
            places.append(SelectOption(label=label, value=f"row:{index}", emoji="🔘"))
    return options + [place for place in places if _changes_layout(session, draft, place.value)]


def place_item(session: BuilderSession, draft: ItemDraft, target: str) -> str | None:
    """Put the button where `target` (a value from `placement_options`) says. Returns an error text, or `None`.

    On failure the layout is left exactly as it was.
    """
    if target == UNPLACE_VALUE:
        unplace_item(session, draft.id)
        return None

    if draft.is_form:
        return _t(session, "errors.placement_form")
    if session.webhook.enabled and not draft.is_link:
        return _t(session, "errors.placement_webhook")
    if draft.is_select and not draft.options:
        return _t(session, "errors.placement_select_empty")

    kind, _, raw_index = target.partition(":")
    rows = session.button_rows
    target_row: list[int] | None = None
    if kind == "row" and raw_index.isdecimal() and int(raw_index) < len(rows):
        target_row = rows[int(raw_index)]
    elif kind != NEW_ROW_VALUE:
        return _t(session, "errors.placement_target_gone")

    snapshot = copy.deepcopy(rows)
    for row in rows:
        if draft.id in row:
            row.remove(draft.id)
    # Rows left empty disappear - except the one the button is about to go into.
    rows[:] = [row for row in rows if row or row is target_row]

    error: str | None = None
    if target_row is not None:
        if not row_has_room(_drafts(session, target_row), draft):
            error = _t(session, "errors.placement_row_full")
        else:
            target_row.append(draft.id)
    elif len(rows) >= MAX_ROWS:
        error = _t(session, "errors.placement_full")
    else:
        rows.append([draft.id])

    if error is not None:
        rows[:] = snapshot
    return error


def rows_to_data(session: BuilderSession) -> list[list[dict[str, object]]]:
    """The button rows with their buttons stored inline, as a template keeps them."""
    rows: list[list[dict[str, object]]] = []
    for row in session.button_rows:
        drafts = (session.library.get(item_id) for item_id in row)
        rows.append([template_data(session.library, draft) for draft in drafts if draft is not None])
    return [row for row in rows if row]


def restore_rows(session: BuilderSession, rows: list[list[dict[str, object]]]) -> int:
    """Replace the session's buttons with the stored rows of a template; returns how many buttons were left out.

    Never trusts the stored data (a row may be hand-edited or written by an older version), and leaves out
    what cannot be used: more than the limits allow, and - while a webhook sender is set - buttons that run actions.
    """
    session.library.clear()
    session.button_rows = []
    session.active_item_id = None

    dropped = 0
    for stored in rows:
        ids: list[int] = []
        for data in stored:
            draft = ItemDraft.from_data(0, data)
            usable = (
                draft is not None
                and len(ids) < BUTTONS_PER_ROW
                and len(session.button_rows) < MAX_ROWS
                and not session.library.is_full
                and not (session.webhook.enabled and not draft.is_link)
            )
            if not usable or draft is None:
                dropped += 1
                continue
            ids.append(session.library.add(draft).id)
            adopt_forms(session.library, draft, data.get("forms") if isinstance(data, dict) else None)
        if ids:
            session.button_rows.append(ids)
    return dropped


def import_rows(session: BuilderSession, message: Message, records: dict[int, InteractiveItemRecord]) -> None:
    """Take the button rows of an existing message over into the session (what cannot be used is left out)."""
    for component in message.components:
        if not isinstance(component, api_components.ActionRow) or len(session.button_rows) >= MAX_ROWS:
            continue

        ids: list[int] = []
        for candidate in component.children:
            if len(ids) >= BUTTONS_PER_ROW:
                continue
            draft = import_component(session.library, session.guild_id, candidate, records)
            if draft is not None:
                ids.append(draft.id)
        if ids:
            session.button_rows.append(ids)


def build_view(session: BuilderSession) -> View | None:
    """The view with the message's real buttons (interactive ones must be stored), or `None` if it has none."""
    view = View(timeout=None)
    for row_index, row in enumerate(session.button_rows):
        for item_id in row:
            draft = session.library.get(item_id)
            if draft is None:
                continue
            item = final_component(draft)
            item.row = row_index
            view.add_item(item)
    return view if view.children else None
