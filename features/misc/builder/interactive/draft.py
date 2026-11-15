from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from discord import ButtonStyle

from core.discord_api.limits import (
    MAX_BUTTON_LABEL,
    MAX_BUTTON_URL,
    MAX_MODAL_TITLE,
    MAX_SELECT_ITEMS,
    MAX_SELECT_OPTION_DESCRIPTION,
    MAX_SELECT_OPTION_LABEL,
    MAX_SELECT_PLACEHOLDER,
)
from features.misc.builder.interactive.models import (
    MAX_QUESTIONS_PER_FORM,
    Action,
    ActionType,
    FormConfig,
    ItemConfig,
    OptionConfig,
    Question,
    SelectConfig,
    SelectMode,
)
from features.misc.builder.validation import is_valid_url

MAX_ITEMS_PER_MESSAGE: int = 25
"""Buttons, dropdowns and forms a single message may define - the most Discord shows on a classic message."""
MAX_EMOJI_LENGTH: int = 100
BUTTONS_PER_ROW: int = 5
"""Discord shows at most five buttons in one row - a dropdown takes a whole row for itself."""

# The styles a user can pick for an interactive button, by the value stored in the form.
BUTTON_STYLES: dict[str, ButtonStyle] = {
    "primary": ButtonStyle.primary,
    "secondary": ButtonStyle.secondary,
    "success": ButtonStyle.success,
    "danger": ButtonStyle.danger,
}


class DraftKind(StrEnum):
    """What a draft turns into: a link button (just opens a URL), a button or a dropdown (both run actions), or a
    form - which is never placed in the message but opened by a button or dropdown option."""

    LINK = "link"
    BUTTON = "button"
    SELECT = "select"
    FORM = "form"


@dataclass
class OptionDraft:
    """One option of a dropdown as the builder edits it. In a role dropdown it stands for `role_id`."""

    key: str
    """The option's value in the dropdown, unique within it; what Discord reports back when it is selected."""
    label: str
    emoji: str | None = None
    description: str | None = None
    config: ItemConfig = field(default_factory=ItemConfig)
    role_id: int | None = None

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in a template."""
        data: dict[str, object] = {"label": self.label, "config": self.config.to_data()}
        if self.emoji:
            data["emoji"] = self.emoji
        if self.description:
            data["description"] = self.description
        if self.role_id is not None:
            data["role_id"] = self.role_id
        return data

    @classmethod
    def from_data(cls, key: str, data: object) -> OptionDraft | None:
        """Rebuild an option from its stored form under the given `key`, or `None` if it is unusable."""
        if not isinstance(data, dict):
            return None

        label = data.get("label")
        emoji = data.get("emoji")
        description = data.get("description")
        role_id = data.get("role_id")
        if not isinstance(label, str) or not label.strip():
            return None
        return cls(
            key=key,
            label=label[:MAX_SELECT_OPTION_LABEL],
            emoji=emoji if isinstance(emoji, str) and 0 < len(emoji) <= MAX_EMOJI_LENGTH else None,
            description=description[:MAX_SELECT_OPTION_DESCRIPTION]
            if isinstance(description, str) and description
            else None,
            config=ItemConfig.from_data(data.get("config")),
            role_id=role_id if isinstance(role_id, int) and not isinstance(role_id, bool) else None,
        )


def open_form_ids(config: ItemConfig) -> list[int]:
    """The ids of the forms the actions of a config open."""
    return [
        action.form_id for action in config.actions if action.type is ActionType.OPEN_FORM and action.form_id is not None
    ]


def remap_forms(config: ItemConfig, form_ids: Mapping[int, int | None]) -> ItemConfig:
    """A copy of `config` whose "open form" actions point to other ids; those that map to nothing are left out."""
    actions: list[Action] = []
    for action in config.actions:
        if action.type is ActionType.OPEN_FORM:
            new_id = form_ids.get(action.form_id) if action.form_id is not None else None
            if new_id is None:
                continue
            action = replace(action, form_id=new_id)
        actions.append(action)

    return ItemConfig(actions=actions, conditions=list(config.conditions))


@dataclass
class ItemDraft:
    """One button, dropdown or form as the builder edits it, before it is sent.

    Nothing about it is stored in the database until the message is sent (`db_id` stays `None`
    until then) - except while editing a message, where `db_id` is the row of the existing item.
    """

    id: int
    kind: DraftKind
    label: str | None = None
    """The text of a button - or the title of a form."""
    emoji: str | None = None
    style: ButtonStyle = ButtonStyle.secondary
    url: str | None = None
    config: ItemConfig = field(default_factory=ItemConfig)
    """A button's actions and conditions; for a dropdown only its conditions (they hold for every option);
    for a form the actions it runs once submitted, and its conditions."""
    mode: SelectMode = SelectMode.STRINGS
    placeholder: str | None = None
    min_values: int = 1
    max_values: int = 1
    options: list[OptionDraft] = field(default_factory=list)
    next_option: int = 1
    questions: list[Question] = field(default_factory=list)
    db_id: int | None = None

    @property
    def is_link(self) -> bool:
        """Whether this is a link button (which needs no bot-side handling at all)."""
        return self.kind is DraftKind.LINK

    @property
    def is_select(self) -> bool:
        """Whether this is a dropdown."""
        return self.kind is DraftKind.SELECT

    @property
    def is_form(self) -> bool:
        """Whether this is a form."""
        return self.kind is DraftKind.FORM

    def option(self, key: str) -> OptionDraft | None:
        """The option with this key, or `None`."""
        return next((option for option in self.options if option.key == key), None)

    def add_option(self, label: str, **fields: object) -> OptionDraft:
        """Append an option with a fresh key; `fields` are `OptionDraft` attributes."""
        option = OptionDraft(key=f"o{self.next_option}", label=label, **fields)  # type: ignore[arg-type]
        self.next_option += 1
        self.options.append(option)
        return option

    def selection_range(self, *, limit_to_options: bool = True) -> tuple[int, int]:
        """The fewest and most options a user may pick. By default limited to what the dropdown actually offers - that
        is what Discord is told; without the limit it is what was set, whatever options there are (yet)."""
        offered = max(len(self.options), 1) if limit_to_options else MAX_SELECT_ITEMS
        maximum = min(max(self.max_values, 1), offered, MAX_SELECT_ITEMS)
        return min(max(self.min_values, 0), maximum), maximum

    def configs(self) -> list[ItemConfig]:
        """Every config holding actions: the item's own, and those of the options of a dropdown."""
        return [self.config, *(option.config for option in self.options)]

    def referenced_form_ids(self) -> list[int]:
        """The ids of the forms this item opens, once each in order."""
        ids: dict[int, None] = {}
        for config in self.configs():
            ids.update(dict.fromkeys(open_form_ids(config)))
        return list(ids)

    def drop_form_actions(self, form_id: int) -> None:
        """Remove the actions that open the given form (it no longer exists)."""
        for config in self.configs():
            config.actions[:] = [
                action
                for action in config.actions
                if not (action.type is ActionType.OPEN_FORM and action.form_id == form_id)
            ]

    def stored_config_data(self, form_ids: Mapping[int, int | None] | None = None) -> dict[str, object]:
        """What the database keeps for the item: the behaviour, not the look (that is on the message).

        `form_ids` maps the ids of form drafts to the ids of their database rows, which is what stored
        "open form" actions refer to.
        """
        ids = form_ids or {}
        if self.is_form:
            config = remap_forms(self.config, ids)
            return FormConfig(
                title=self.label or "", questions=list(self.questions), actions=config.actions, conditions=config.conditions
            ).to_data()

        if not self.is_select:
            return remap_forms(self.config, ids).to_data()

        select = SelectConfig(
            mode=self.mode,
            conditions=self.config.conditions,
            options=[OptionConfig(option.key, remap_forms(option.config, ids), option.role_id) for option in self.options],
        )
        return select.to_data()

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in a template."""
        data: dict[str, object] = {"kind": self.kind.value}
        if self.label:
            data["label"] = self.label
        if self.emoji:
            data["emoji"] = self.emoji
        if self.is_link:
            data["url"] = self.url
        elif self.is_form:
            data["questions"] = [question.to_data() for question in self.questions]
            data["config"] = self.config.to_data()
        elif self.is_select:
            data["mode"] = self.mode.value
            data["placeholder"] = self.placeholder
            data["min_values"] = self.min_values
            data["max_values"] = self.max_values
            data["config"] = self.config.to_data()
            data["options"] = [option.to_data() for option in self.options]
        else:
            data["style"] = self.style.value
            data["config"] = self.config.to_data()
        return data

    @classmethod
    def from_data(cls, item_id: int, data: object) -> ItemDraft | None:
        """Rebuild a draft from its stored form, or `None` if it is unusable.

        Never trusts the payload: a template may be hand-edited or written by an older version.
        """
        if not isinstance(data, dict):
            return None

        raw_kind = data.get("kind")
        if not isinstance(raw_kind, str) or raw_kind not in DraftKind:
            return None
        kind = DraftKind(raw_kind)

        if kind is DraftKind.SELECT:
            return cls._select_from_data(item_id, data)
        if kind is DraftKind.FORM:
            return cls._form_from_data(item_id, data)

        label = data.get("label")
        emoji = data.get("emoji")
        label = label[:MAX_BUTTON_LABEL] if isinstance(label, str) and label else None
        emoji = emoji if isinstance(emoji, str) and 0 < len(emoji) <= MAX_EMOJI_LENGTH else None
        if label is None and emoji is None:
            return None

        if kind is DraftKind.LINK:
            url = data.get("url")
            if not isinstance(url, str) or len(url) > MAX_BUTTON_URL or not is_valid_url(url):
                return None
            return cls(id=item_id, kind=kind, label=label, emoji=emoji, url=url)

        raw_style = data.get("style")
        style = next((known for known in BUTTON_STYLES.values() if known.value == raw_style), ButtonStyle.secondary)
        return cls(
            id=item_id, kind=kind, label=label, emoji=emoji, style=style, config=ItemConfig.from_data(data.get("config"))
        )

    @classmethod
    def _select_from_data(cls, item_id: int, data: dict[str, object]) -> ItemDraft:
        """Rebuild a dropdown draft; unusable options are left out and every option gets a fresh key."""
        raw_mode = data.get("mode")
        placeholder = data.get("placeholder")
        minimum, maximum = data.get("min_values"), data.get("max_values")
        draft = cls(
            id=item_id,
            kind=DraftKind.SELECT,
            mode=SelectMode(raw_mode) if isinstance(raw_mode, str) and raw_mode in SelectMode else SelectMode.STRINGS,
            placeholder=placeholder[:MAX_SELECT_PLACEHOLDER] if isinstance(placeholder, str) and placeholder else None,
            min_values=minimum if isinstance(minimum, int) and not isinstance(minimum, bool) else 1,
            max_values=maximum if isinstance(maximum, int) and not isinstance(maximum, bool) else 1,
            config=ItemConfig.from_data(data.get("config")),
        )
        stored = data.get("options")
        for entry in stored if isinstance(stored, list) else []:
            if len(draft.options) >= MAX_SELECT_ITEMS:
                break
            option = OptionDraft.from_data(f"o{draft.next_option}", entry)
            if option is not None:
                draft.options.append(option)
                draft.next_option += 1
        return draft

    @classmethod
    def _form_from_data(cls, item_id: int, data: dict[str, object]) -> ItemDraft:
        """Rebuild a form draft; unusable questions are left out."""
        title, stored = data.get("label"), data.get("questions")
        questions = [Question.from_data(entry) for entry in stored] if isinstance(stored, list) else []
        return cls(
            id=item_id,
            kind=DraftKind.FORM,
            label=title[:MAX_MODAL_TITLE] if isinstance(title, str) and title else None,
            config=ItemConfig.from_data(data.get("config")),
            questions=[question for question in questions if question is not None][:MAX_QUESTIONS_PER_FORM],
        )


def template_data(library: InteractiveLibrary, draft: ItemDraft) -> dict[str, object]:
    """The JSON-able form of an item as a template keeps it: the item plus - inline - the forms it opens, so a
    template stays complete without the library of the session that saved it."""
    data = draft.to_data()
    forms = {
        str(form_id): form.to_data()
        for form_id in draft.referenced_form_ids()
        if (form := library.get(form_id)) is not None and form.is_form
    }
    if forms:
        data["forms"] = forms
    return data


def adopt_forms(library: InteractiveLibrary, draft: ItemDraft, stored: object) -> None:
    """Give an item that was loaded from a template the forms its actions open.

    `stored` is the template's inline form data (see `template_data`). Every action gets a form of its own, as a
    form belongs to exactly one action. Actions whose form is unusable, or does not fit into the library any
    more, are dropped.
    """
    stored_forms = stored if isinstance(stored, dict) else {}

    def resolve(old_id: int) -> int | None:
        """The draft id of a new form made from the stored form `old_id`."""
        form = ItemDraft.from_data(0, stored_forms.get(str(old_id)))
        if form is None or not form.is_form or library.is_full:
            return None
        return library.add(form).id

    for config in draft.configs():
        ids = {old_id: resolve(old_id) for old_id in open_form_ids(config)}
        config.actions[:] = remap_forms(config, ids).actions


def row_has_room(row: Sequence[ItemDraft], draft: ItemDraft) -> bool:
    """Whether `draft` can join the items already in `row`: up to five buttons, or a dropdown on its own."""
    if draft.is_select:
        return not row
    return len(row) < BUTTONS_PER_ROW and not any(other.is_select for other in row)


@dataclass
class InteractiveLibrary:
    """Every button, dropdown and form the user defined for the message being built, placed or not.

    Where a button or dropdown sits in the message is not stored here but derived from the builder's own
    layout (rows, accessories), so deleting a row can never leave a stale placement behind.
    """

    items: dict[int, ItemDraft] = field(default_factory=dict)
    loaded_db_ids: set[int] = field(default_factory=set)
    """The rows of the items that were on the message when it was loaded for editing; those that are
    no longer placed when the changes are saved get deleted."""
    next_id: int = 1

    @property
    def is_full(self) -> bool:
        """Whether no further item may be defined."""
        return len(self.items) >= MAX_ITEMS_PER_MESSAGE

    def add(self, draft: ItemDraft) -> ItemDraft:
        """Register a draft; its `id` is set here."""
        draft.id = self.next_id
        self.next_id += 1
        self.items[draft.id] = draft
        return draft

    def new_draft(self, kind: DraftKind, **fields: object) -> ItemDraft:
        """Create and register a draft of the given kind; `fields` are `ItemDraft` attributes."""
        return self.add(ItemDraft(id=0, kind=kind, **fields))  # type: ignore[arg-type]

    def get(self, item_id: int) -> ItemDraft | None:
        """The draft with this id, or `None`."""
        return self.items.get(item_id)

    def remove(self, item_id: int) -> None:
        """Forget a draft. The caller removes it from the layout as well. The actions that opened a form that is
        removed go with it."""
        removed = self.items.pop(item_id, None)
        if removed is None:
            return

        if removed.is_form:
            for draft in self.items.values():
                draft.drop_form_actions(item_id)
        else:
            self.prune_forms()

    def form_owner(self, form_id: int) -> tuple[ItemDraft, str | None] | None:
        """The button or dropdown - and the key of its option - whose action opens the form, or `None`. A form
        belongs to the action that opens it."""
        for draft in self.items.values():
            if draft.is_form:
                continue
            if form_id in open_form_ids(draft.config):
                return draft, None
            for option in draft.options:
                if form_id in open_form_ids(option.config):
                    return draft, option.key
        return None

    def prune_forms(self) -> None:
        """Forget the forms no action opens any more: a form only exists as part of the action that opens it."""
        used = {form_id for draft in self.items.values() if not draft.is_form for form_id in draft.referenced_form_ids()}
        for form in self.forms():
            if form.id not in used:
                del self.items[form.id]

    def ordered(self) -> list[ItemDraft]:
        """All drafts in the order they were created."""
        return list(self.items.values())

    def interactive(self) -> list[ItemDraft]:
        """The drafts that run actions (everything but link buttons)."""
        return [draft for draft in self.items.values() if not draft.is_link]

    def elements(self) -> list[ItemDraft]:
        """The clickable elements - buttons and dropdowns - in the order they are listed."""
        return [draft for draft in self.items.values() if not draft.is_form]

    def forms(self) -> list[ItemDraft]:
        """The forms, in the order they are listed."""
        return [draft for draft in self.items.values() if draft.is_form]

    def move(self, item_id: int, offset: int) -> bool:
        """Move an item up (`offset` -1) or down (+1) among those of its own kind - clickable elements or forms.
        Returns whether it moved. The order only decides how the lists show the items; where a button sits in
        the message is the layout's business."""
        draft = self.items.get(item_id)
        if draft is None:
            return False

        group = [other.id for other in self.items.values() if other.is_form == draft.is_form]
        target = group.index(item_id) + offset
        return 0 <= target < len(group) and self.swap(item_id, group[target])

    def swap(self, first_id: int, second_id: int) -> bool:
        """Let two items trade places in the list. Returns whether both exist."""
        if first_id not in self.items or second_id not in self.items:
            return False

        order = list(self.items)
        first, second = order.index(first_id), order.index(second_id)
        order[first], order[second] = order[second], order[first]
        reordered = {key: self.items[key] for key in order}
        self.items.clear()
        self.items.update(reordered)
        return True

    def referenced_forms(self, drafts: Sequence[ItemDraft]) -> list[ItemDraft]:
        """The forms opened by these items, once each in order - the ones that have to be stored along with them."""
        ids: dict[int, None] = {}
        for draft in drafts:
            ids.update(dict.fromkeys(draft.referenced_form_ids()))
        return [form for form_id in ids if (form := self.items.get(form_id)) is not None and form.is_form]

    def clear(self) -> None:
        """Forget all drafts, e.g. before a template replaces the whole layout.

        `loaded_db_ids` is kept on purpose: the stored items of the message being edited are still
        there until the changes are saved.
        """
        self.items.clear()
