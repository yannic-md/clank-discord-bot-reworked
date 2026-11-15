import re

from discord import components as api_components

from core.db.repositories.interactive_builder.interactive_item_repository import InteractiveItemRecord
from features.misc.builder.interactive.draft import (
    MAX_EMOJI_LENGTH,
    DraftKind,
    InteractiveLibrary,
    ItemDraft,
    OptionDraft,
    open_form_ids,
    remap_forms,
)
from features.misc.builder.interactive.models import ItemConfig, ItemKind, SelectConfig
from features.misc.builder.interactive.runtime import BUTTON_PREFIX, SELECT_PREFIX
from features.misc.builder.interactive.store import draft_from_record, form_draft_from_record

_BUTTON_ID: re.Pattern[str] = re.compile(rf"{BUTTON_PREFIX}:(\d+)")
_SELECT_ID: re.Pattern[str] = re.compile(rf"{SELECT_PREFIX}:(\d+)")
_OPTION_KEY: re.Pattern[str] = re.compile(r"o(\d+)")


def adopt_stored_forms(
    library: InteractiveLibrary, guild_id: int, draft: ItemDraft, records: dict[int, InteractiveItemRecord]
) -> None:
    """Give an imported button or dropdown the forms it opens: their stored rows are taken over as form drafts, and
    the "open form" actions - which hold database ids when stored - point to those drafts instead. Actions whose
    form is gone are dropped."""

    def resolve(db_id: int) -> int | None:
        """The draft id of the form stored as `db_id`, adding it to the library on first use."""
        existing = next((form for form in library.forms() if form.db_id == db_id), None)
        if existing is not None:
            return existing.id

        record = records.get(db_id)
        if record is None or record.guild_id != guild_id or record.kind != ItemKind.FORM.value or library.is_full:
            return None
        return form_draft_from_record(library, record).id

    for config in draft.configs():
        ids = {db_id: resolve(db_id) for db_id in open_form_ids(config)}
        config.actions[:] = remap_forms(config, ids).actions


def import_button(
    library: InteractiveLibrary,
    guild_id: int,
    button: api_components.Button,
    records: dict[int, InteractiveItemRecord],
) -> ItemDraft | None:
    """Take a received button into `library`: a link button as it is, one of the bot's own interactive
    buttons together with its stored behaviour. Anything else (other bots' buttons, premium buttons,
    buttons whose stored item is gone or belongs to another server) is not supported and gives `None`.

    `records` are the stored items of the message the button came from, by id.
    """
    emoji = str(button.emoji) if button.emoji else None
    if library.is_full or (not button.label and not emoji) or (emoji and len(emoji) > MAX_EMOJI_LENGTH):
        return None

    if button.url:
        return library.new_draft(DraftKind.LINK, label=button.label, emoji=emoji, url=button.url)

    match = _BUTTON_ID.fullmatch(button.custom_id or "")
    record = records.get(int(match.group(1))) if match else None
    if record is None or record.guild_id != guild_id or record.kind != ItemKind.BUTTON.value:
        return None
    draft = draft_from_record(library, record, label=button.label, emoji=emoji, style=button.style)
    adopt_stored_forms(library, guild_id, draft, records)
    return draft


def import_select(
    library: InteractiveLibrary,
    guild_id: int,
    menu: api_components.SelectMenu,
    records: dict[int, InteractiveItemRecord],
) -> ItemDraft | None:
    """Take a received dropdown of the bot into `library`, together with the stored behaviour of its options.

    The message holds how the dropdown looks (placeholder, labels, emoji, limits), the stored item what each
    option does. Dropdowns of other bots, or whose stored item is gone, are not supported and give `None`.
    """
    match = _SELECT_ID.fullmatch(menu.custom_id or "")
    record = records.get(int(match.group(1))) if match else None
    if library.is_full or record is None or record.guild_id != guild_id or record.kind != ItemKind.SELECT.value:
        return None

    stored = SelectConfig.from_data(record.config_data)
    draft = library.new_draft(
        DraftKind.SELECT,
        mode=stored.mode,
        placeholder=menu.placeholder,
        min_values=menu.min_values,
        max_values=menu.max_values,
        config=ItemConfig(conditions=stored.conditions),
        db_id=record.id,
    )
    for option in menu.options:
        behaviour = stored.option(option.value)
        draft.options.append(
            OptionDraft(
                key=option.value,
                label=option.label,
                emoji=str(option.emoji) if option.emoji else None,
                description=option.description,
                config=behaviour.config if behaviour is not None else ItemConfig(),
                role_id=behaviour.role_id if behaviour is not None else None,
            )
        )
        number = _OPTION_KEY.fullmatch(option.value)
        if number is not None:
            draft.next_option = max(draft.next_option, int(number.group(1)) + 1)

    library.loaded_db_ids.add(record.id)
    adopt_stored_forms(library, guild_id, draft, records)
    return draft


def import_component(
    library: InteractiveLibrary,
    guild_id: int,
    component: api_components.Component,
    records: dict[int, InteractiveItemRecord],
) -> ItemDraft | None:
    """Take a received button or dropdown into `library`; `None` for anything that is not supported."""
    if isinstance(component, api_components.Button):
        return import_button(library, guild_id, component, records)
    if isinstance(component, api_components.SelectMenu):
        return import_select(library, guild_id, component, records)
    return None


def forget_stored_ids(library: InteractiveLibrary) -> None:
    """Detach every item from its stored row, so that sending creates new ones instead of touching the
    originals - for a message that is copied instead of edited."""
    for draft in library.items.values():
        draft.db_id = None
    library.loaded_db_ids.clear()
