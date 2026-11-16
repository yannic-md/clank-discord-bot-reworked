from collections.abc import Callable, Iterable
from typing import Any

from discord import Interaction, SelectOption

from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.interactive.draft import DraftKind, InteractiveLibrary, ItemDraft, OptionDraft
from features.misc.builder.interactive.editor import (
    BUTTON_EMOJI,
    DROPDOWN_EMOJI,
    LINK_EMOJI,
    ROLE_DROPDOWN_EMOJI,
    draft_name,
    draft_option,
)
from features.misc.builder.interactive.messages import screen, t
from features.misc.builder.interactive.modals import AfterButton, ButtonModal, SelectLookModal
from features.misc.builder.interactive.models import INTERACTIVE_EMOJI, SelectMode

EDIT_EMOJI: str = "✏️"
"""The emoji in the heading of every screen on which something is changed."""

KIND_LINK: str = "link"
KIND_BUTTON: str = "button"
KIND_TEXTS: str = "select_strings"
KIND_ROLES: str = "select_roles"
KIND_EMOJIS: dict[str, str] = {
    KIND_BUTTON: BUTTON_EMOJI,
    KIND_LINK: LINK_EMOJI,
    KIND_TEXTS: DROPDOWN_EMOJI,
    KIND_ROLES: ROLE_DROPDOWN_EMOJI,
}


def hub_text(language: SupportedLanguage, key: str, **variables: Any) -> str:
    """A text of the "Buttons & Dropdowns" screen (`hub.*` in the interactive locale domain)."""
    return t(language, f"hub.{key}", **variables)


def hub_title(language: SupportedLanguage) -> str:
    """The heading of the overview: what the screen is called in the main menu, with its emoji."""
    return f"{INTERACTIVE_EMOJI} ~ {translate(language, 'builder.select.interactive.label')}"


def owned_counts(library: InteractiveLibrary, item_ids: Iterable[int]) -> tuple[int, int]:
    """How many buttons and how many dropdowns these items are: a button with a link is a button too, and a dropdown
    of roles is a dropdown like one of texts."""
    drafts = [draft for item_id in item_ids if (draft := library.get(item_id)) is not None and not draft.is_form]
    dropdowns = sum(1 for draft in drafts if draft.is_select)
    return len(drafts) - dropdowns, dropdowns


def owned_text(language: SupportedLanguage, buttons: int, dropdowns: int) -> str | None:
    """What a message has in the way of clickable elements - "Has 2 buttons and 1 dropdown" - or `None` if it has none.
    A kind it has none of is left out."""
    parts: list[str] = []
    if buttons:
        parts.append(t(language, "hub.owned.buttons", count=buttons))
    if dropdowns:
        parts.append(t(language, "hub.owned.dropdowns", count=dropdowns))
    if not parts:
        return None

    items = parts[0] if len(parts) == 1 else t(language, "hub.owned.both", buttons=parts[0], dropdowns=parts[1])
    return t(language, "hub.owned.summary", items=items)


def placement_text(language: SupportedLanguage, rules: str, layout: str, *, shown: int, total: int) -> str:
    """The info text of the placement screen once something sits in the message: what the screen is for, what the
    builder says about where an element may go (`rules`), and under a bold heading the placed elements (`layout`; with
    none there is no heading either). When the screen can preview only `shown` of the `total` rows, it says so."""
    lines = [screen(language, "placement.description"), "", rules]
    if layout:
        lines += ["", f"**{screen(language, 'placement.list')}:**", layout]
    if total > shown:
        lines += ["", screen(language, "placement.truncated", shown=shown, total=total)]
    return "\n".join(lines)


def _code(text: str) -> str:
    """The text as a code span. A custom emoji is not in it (see `draft_name`), and a backtick would end the span."""
    return f"`{text.replace('`', chr(39))}`"


def element_name(language: SupportedLanguage, draft: ItemDraft) -> str:
    """The name of an element in a code span, for titles and sentences. A custom emoji is left out of it."""
    return _code(draft_name(language, draft, plain=True))


def option_name(option: OptionDraft) -> str:
    """The name of an option of a dropdown in a code span, for titles."""
    return _code(option.label)


def item_title(language: SupportedLanguage, draft: ItemDraft) -> str:
    """The heading of the screen of a selected element: "Edit button" or "Edit dropdown", with a gear."""
    kind = "select" if draft.is_select else "button"
    return f"{EDIT_EMOJI} ~ {hub_text(language, f'item.title.{kind}')}"


def item_description(language: SupportedLanguage, draft: ItemDraft, *, preview: bool) -> str:
    """The info text above a selected element: that it is managed here with the settings below. The name is in a
    code span; a dropdown that has no placeholder is called by what it is, so the sentence reads "the `Dropdown`".
    `preview` adds where the preview of the element is (next to the button that places it). Only a button has one -
    a dropdown is not previewed, so nothing points to it."""
    name = _code(draft_name(language, draft, plain=True))
    if draft.is_select:
        key = "item.description.select" if draft.placeholder else "item.description.select_unnamed"
    else:
        key = "item.description.button"
    text = hub_text(language, key, name=name)
    if not preview:
        return text

    return text if draft.is_select else f"{text} {hub_text(language, 'item.preview')}"


def delete_label(language: SupportedLanguage, draft: ItemDraft) -> str:
    """The label of the button that deletes the selected element: "Delete button" or "Delete dropdown"."""
    return hub_text(language, f"delete.{'select' if draft.is_select else 'button'}")


def form_title(language: SupportedLanguage) -> str:
    """The heading of the screen of a form, with a gear."""
    return f"{EDIT_EMOJI} ~ {hub_text(language, 'form_view.title')}"


def form_description(language: SupportedLanguage, form: ItemDraft) -> str:
    """The info text above a form: that it is managed here with the settings below."""
    return hub_text(language, "form_view.description", name=_code(draft_name(language, form, plain=True)))


def overview_text(language: SupportedLanguage, *, webhook: bool) -> str:
    """What the screen is for, shown while nothing is selected: what a clickable element is and that its actions
    are set once it is selected - and, while a custom sender is set, why only link buttons are on offer."""
    lines = [hub_text(language, "overview.elements"), hub_text(language, "overview.actions")]
    if webhook:
        lines.append(hub_text(language, "webhook_note"))
    return "\n\n".join(lines)


def kind_view_text(language: SupportedLanguage, *, webhook: bool) -> str:
    """The explanation on the screen that asks which kind of element to create; with a custom sender it adds
    that only link buttons are possible."""
    text = hub_text(language, "kind_view.description")
    return f"{text}\n\n{hub_text(language, 'webhook_note')}" if webhook else text


def element_kinds(*, webhook: bool) -> list[str]:
    """The kinds of clickable element that can be created. A custom sender is a webhook, and webhooks can only
    send link buttons."""
    return [KIND_LINK] if webhook else [KIND_BUTTON, KIND_LINK, KIND_TEXTS, KIND_ROLES]


def kind_options(language: SupportedLanguage, kinds: list[str]) -> list[SelectOption]:
    """The dropdown entries that let the user pick what kind of clickable element to create."""
    return [
        SelectOption(
            label=t(language, f"hub.kinds.{kind}.label"),
            description=t(language, f"hub.kinds.{kind}.description"),
            value=kind,
            emoji=KIND_EMOJIS[kind],
        )
        for kind in kinds
    ]


def ordered_elements(library: InteractiveLibrary, is_placed: Callable[[int], bool]) -> list[ItemDraft]:
    """The clickable elements as they are listed: those that are not in the message yet first, the placed ones
    last (each group in its own order). `is_placed` tells whether an element sits in the message."""
    elements = library.elements()
    return [draft for draft in elements if not is_placed(draft.id)] + [draft for draft in elements if is_placed(draft.id)]


def order_group(library: InteractiveLibrary, draft: ItemDraft, is_placed: Callable[[int], bool]) -> list[ItemDraft]:
    """The elements `draft` can be moved among: those that are in the same state - placed or not - in list order."""
    placed = is_placed(draft.id)
    return [other for other in ordered_elements(library, is_placed) if is_placed(other.id) == placed]


def element_options(
    language: SupportedLanguage,
    library: InteractiveLibrary,
    *,
    active_id: int | None,
    is_placed: Callable[[int], bool],
    place_of: Callable[[int], str | None] | None = None,
) -> list[SelectOption]:
    """The entries of the clickable-elements dropdown: every button and dropdown, the placed ones last. `place_of`
    names where a placed element sits (a row), which the entry says first."""
    return [
        draft_option(
            language,
            draft,
            default=draft.id == active_id,
            placed=is_placed(draft.id),
            place=place_of(draft.id) if place_of is not None else None,
        )
        for draft in ordered_elements(library, is_placed)
    ]


async def start_element(
    interaction: Interaction,
    language: SupportedLanguage,
    library: InteractiveLibrary,
    kind: str,
    after: AfterButton,
) -> None:
    """Begin creating a clickable element of the given kind: the modal for how it looks opens - the details of a
    button, the placeholder and limits of a dropdown - and `after` runs once it is done. Nothing exists before that."""
    if kind in (KIND_LINK, KIND_BUTTON):
        draft_kind = DraftKind.LINK if kind == KIND_LINK else DraftKind.BUTTON
        await interaction.response.send_modal(ButtonModal(language, library, draft_kind, None, after))
        return

    mode = SelectMode.STRINGS if kind == KIND_TEXTS else SelectMode.ROLES
    await interaction.response.send_modal(SelectLookModal(language, None, after, library=library, mode=mode))


def element_after(library: InteractiveLibrary, item_id: int, is_placed: Callable[[int], bool]) -> int | None:
    """The element to select once `item_id` is deleted: the one that follows it in the list of the elements - the one
    before it if it was the last - or `None` if no other element exists. Call it before the element is deleted."""
    listed = [draft.id for draft in ordered_elements(library, is_placed)]
    if item_id not in listed:
        return None

    position = listed.index(item_id)
    listed.remove(item_id)
    return listed[min(position, len(listed) - 1)] if listed else None
