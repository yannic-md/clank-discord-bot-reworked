import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Any

from discord import SelectOption

from core.enums.language import SupportedLanguage
from features.misc.builder.interactive.draft import InteractiveLibrary, ItemDraft, OptionDraft
from features.misc.builder.interactive.messages import permission_names, t
from features.misc.builder.interactive.models import (
    MAX_ACTIONS_PER_ITEM,
    MAX_CONDITIONS_PER_ITEM,
    MESSAGE_ACTIONS,
    ROLE_ACTIONS,
    ROLE_CONDITIONS,
    Action,
    ActionType,
    Condition,
    ConditionType,
    ConfigProblem,
    MessagePayload,
    PayloadKind,
    Question,
    SelectMode,
    clashing_action_roles,
    conflicting_roles,
    needless_role_changes,
)

ACTION_EMOJIS: dict[ActionType, str] = {
    ActionType.ROLE_ADD: "➕",
    ActionType.ROLE_REMOVE: "➖",
    ActionType.ROLE_TOGGLE: "🔁",
    ActionType.ROLE_SET: "🎯",
    ActionType.REPLY: "💬",
    ActionType.DM_USER: "✉️",
    ActionType.SEND_CHANNEL: "📨",
    ActionType.DELETE_MESSAGE: "🗑️",
    ActionType.OPEN_FORM: "📋",
}

CONDITION_EMOJIS: dict[ConditionType, str] = {
    ConditionType.ROLE_REQUIRED: "🔒",
    ConditionType.ROLE_FORBIDDEN: "🚫",
    ConditionType.PERMISSIONS: "🛡️",
    ConditionType.ACCOUNT_AGE: "📅",
    ConditionType.MEMBER_AGE: "🕰️",
    ConditionType.ONCE_PER_USER: "1️⃣",
    ConditionType.COOLDOWN: "⏳",
}

LINK_EMOJI: str = "🔗"
BUTTON_EMOJI: str = "🧩"
DROPDOWN_EMOJI: str = "📚"
ROLE_DROPDOWN_EMOJI: str = "🎭"
FORM_EMOJI: str = "📋"

SECTION_EMOJIS: dict[str, str] = {
    "placement": "📍",
    "link": "🔗",
    "actions": "⚙️",
    "conditions": "🔐",
    "mode": "🔽",
    "choice": "☑️",
    "options": "🧩",
    "questions": "❓",
    "form_actions": "⚙️",
}

BULLET: str = "▫️"
"""Marks an entry of a list that is not numbered - a condition - so it is clear there are several."""
BULLET_ACTIVE: str = "▶️"
"""Marks the selected entry of a list on a screen where one can be picked."""

SECTION_BUDGET: int = 1000
"""How many characters one part of a summary may take. An embed field holds 1024, and each line costs three more
for its quote mark and line break - the rest is room for a blank line below."""

_PAYLOAD_PREVIEW: int = 40
_CUSTOM_EMOJI = re.compile(r"<a?:\w+:\d+>")


def is_custom_emoji(emoji: str | None) -> bool:
    """Whether the emoji is one of a server (`<:name:123>`) rather than a standard one. Only message text shows
    those; in a dropdown entry or a code span Discord writes them out with their id."""
    return emoji is not None and _CUSTOM_EMOJI.fullmatch(emoji) is not None


def draft_emoji(draft: ItemDraft) -> str:
    """The emoji that stands for a kind of item: a link button, a button, a dropdown, a role dropdown or a form."""
    if draft.is_form:
        return FORM_EMOJI
    if draft.is_link:
        return LINK_EMOJI
    if draft.is_select:
        return ROLE_DROPDOWN_EMOJI if draft.mode is SelectMode.ROLES else DROPDOWN_EMOJI
    return BUTTON_EMOJI


def _mentions(role_ids: Collection[int]) -> str:
    """Role mentions of the ids, separated by commas."""
    return ", ".join(f"<@&{role_id}>" for role_id in role_ids)


def describe_payload(language: SupportedLanguage, payload: MessagePayload | None) -> str:
    """A short description of what a message action sends: its text, or the template it is a snapshot of."""
    if payload is None or payload.is_empty:
        return t(language, "editor.payload.empty")

    if payload.kind is PayloadKind.TEXT:
        flat = " ".join(payload.text.split())
        shortened = flat if len(flat) <= _PAYLOAD_PREVIEW else f"{flat[: _PAYLOAD_PREVIEW - 1]}…"
        return t(language, "editor.payload.text", text=shortened.replace("`", "'"))

    name = (payload.template_name or "?").replace("`", "'")
    return t(language, f"editor.payload.{payload.kind.value}", name=name)


def describe_action(language: SupportedLanguage, action: Action, library: InteractiveLibrary | None = None) -> str:
    """One line describing what an action does, for the editor. `library` is needed to name the form of an
    "open form" action."""
    if action.type is ActionType.OPEN_FORM:
        form = library.get(action.form_id) if library is not None and action.form_id is not None else None
        return t(language, "editor.action.open_form", form=draft_name(language, form) if form is not None else "?")
    if action.type is ActionType.ROLE_SET:
        return t(language, "editor.action.role_set", count=len(action.roles), roles=_mentions(action.roles))
    if action.type is ActionType.SEND_CHANNEL:
        channel = f"<#{action.channel_id}>" if action.channel_id is not None else "?"
        return t(language, "editor.action.send_channel", channel=channel, message=describe_payload(language, action.payload))
    if action.type in (ActionType.REPLY, ActionType.DM_USER):
        return t(language, f"editor.action.{action.type.value}", message=describe_payload(language, action.payload))
    if action.type is ActionType.DELETE_MESSAGE:
        return t(language, "editor.action.delete_message")
    return t(language, f"editor.action.{action.type.value}", count=len(action.roles), roles=_mentions(action.roles))


def describe_condition(language: SupportedLanguage, condition: Condition) -> str:
    """One line describing a restriction, for the editor."""
    match condition.type:
        case ConditionType.ROLE_REQUIRED:
            key = "editor.condition.role_required.all" if condition.match_all else "editor.condition.role_required.any"
            return t(language, key, count=len(condition.roles), roles=_mentions(condition.roles))
        case ConditionType.ROLE_FORBIDDEN:
            return t(
                language, "editor.condition.role_forbidden", count=len(condition.roles), roles=_mentions(condition.roles)
            )
        case ConditionType.PERMISSIONS:
            return t(language, "editor.condition.permissions", permissions=permission_names(language, condition.permissions))
        case ConditionType.ONCE_PER_USER:
            return t(language, "editor.condition.once_per_user")
        case _:
            return t(language, f"editor.condition.{condition.type.value}", amount=condition.amount)


def describe_option(language: SupportedLanguage, draft: ItemDraft, option: OptionDraft) -> str:
    """One line describing a dropdown option: how it looks and - in a role dropdown - which role it hands out."""
    name = " ".join(part for part in (option.emoji, option.label) if part)
    if draft.mode is SelectMode.ROLES and option.role_id is not None:
        return t(language, "editor.option_line.role", name=name, role=f"<@&{option.role_id}>")
    count = len(option.config.actions)
    return t(language, "editor.option_line.actions", name=name, amount=count)


def describe_question(language: SupportedLanguage, number: int, question: Question) -> str:
    """One line describing a question of a form: its text and whether it is optional or asks for a longer answer."""
    notes = [
        note
        for note in (
            t(language, "editor.question.optional") if not question.required else "",
            t(language, "editor.question.paragraph") if question.paragraph else "",
        )
        if note
    ]
    suffix = f" ({', '.join(notes)})" if notes else ""
    return f"{number}. {question.label}{suffix}"


@dataclass(frozen=True, slots=True)
class Section:
    """One part of the summary of a button, dropdown or form: what it is about and what it says about it."""

    emoji: str
    name: str
    lines: list[str]
    inline: bool = False
    """Whether it may sit next to others in an embed (short parts: a place, a kind, who may use it)."""
    spaced: bool = False
    """Whether an embed shows a blank line above it. A spaced part always starts a row of its own: what comes before it
    is another row, which ends with the blank line."""
    quoted: bool = True
    """Whether its lines are quoted (`> `). Text the user wrote is shown as it is, so that its formatting can be seen."""
    padded: bool = False
    """Whether a row of two parts that includes it is filled up with an empty third field. Discord sizes the fields of a
    row by how many there are, so rows that are all filled up to three have their fields at the same places."""
    listed: bool = False
    """Whether its lines are a list of what the user added. A text shows a list below its name even when it has just one
    entry; a part of a single line sits behind its name."""
    divided: bool = False
    """Whether a text screen puts a divider line above it, and with it starts a text of its own. An embed has no use for
    that: its fields are set apart by `spaced`."""


def draft_sections(
    language: SupportedLanguage,
    draft: ItemDraft,
    *,
    placement: str | None,
    library: InteractiveLibrary | None = None,
) -> list[Section]:
    """The summary of a button, dropdown or form in parts: where it sits, what it is and does, who may use it. How it
    looks is not in it: the screens show the thing itself. A form has no place of its own; it lists its questions and
    what happens once it is submitted. `library` names the forms the actions open."""

    def section(
        key: str,
        lines: list[str],
        *,
        inline: bool = False,
        spaced: bool = False,
        padded: bool = False,
        listed: bool = False,
        divided: bool = False,
        **variables: Any,
    ) -> Section:
        """A part of the summary named by `editor.section.<key>`. A list too long for it is cut short."""
        name = t(language, f"editor.section.{key}", **variables)
        fitted = fit_lines(lines, lambda hidden: t(language, "editor.section.more", amount=hidden))
        return Section(SECTION_EMOJIS[key], name, fitted, inline, spaced, padded=padded, listed=listed, divided=divided)

    def numbered(texts: list[str], empty: str) -> list[str]:
        """The texts as a numbered list - or the explanation of why there are none."""
        return [f"{number}. {text}" for number, text in enumerate(texts, 1)] or [t(language, empty)]

    # Role mentions are long, so conditions with a role take a row of their own instead of sharing one - and, like
    # a list, a blank line above their name.
    has_role = any(condition.type in ROLE_CONDITIONS for condition in draft.config.conditions)
    conditions = section(
        "conditions",
        [f"{BULLET} {describe_condition(language, condition)}" for condition in draft.config.conditions]
        or [t(language, "editor.summary.no_conditions")],
        inline=not has_role,
        spaced=has_role,
        listed=bool(draft.config.conditions),
    )

    if draft.is_form:
        questions = [describe_question(language, number, question) for number, question in enumerate(draft.questions, 1)]
        on_submit = [describe_action(language, action, library) for action in draft.config.actions]
        # Who may use the form comes first and has a row to itself, what happens once it is submitted follows, and the
        # questions - the longest part - come last; every part after a blank line.
        return [
            replace(conditions, inline=False, spaced=False),
            section(
                "form_actions", numbered(on_submit, "editor.summary.no_form_actions"), spaced=True, listed=bool(on_submit)
            ),
            section(
                "questions",
                questions or [t(language, "editor.summary.no_questions")],
                spaced=True,
                listed=bool(questions),
                amount=len(questions),
            ),
        ]

    placed = section("placement", [placement or t(language, "editor.summary.unplaced")], inline=True, padded=draft.is_select)
    sections = [placed]  # where the element sits is always the first part of what is about the element itself
    if draft.is_link:
        return [*sections, section("link", [draft.url or ""], inline=True, divided=True)]

    if draft.is_select:
        # Like a button: where it sits and who may use it come first, side by side. The kind of dropdown and how it is
        # chosen from follow in a row of their own, after a blank line, and the options again after one. Both rows have
        # three fields (one is empty), so the fields of the one stand exactly where those of the other do.
        minimum, maximum = draft.selection_range(limit_to_options=False)  # what was set, even before there are options
        options = [describe_option(language, draft, option) for option in draft.options]
        return [
            *sections,
            conditions,
            section(
                "mode",
                [t(language, f"editor.summary.mode.{draft.mode.value}")],
                inline=True,
                spaced=True,
                padded=True,
                divided=True,
            ),
            section("choice", [_choice_text(language, minimum, maximum)], inline=True),
            section(
                "options",
                numbered(options, "editor.summary.no_options"),
                spaced=True,
                listed=bool(options),
                divided=True,
                amount=len(options),
            ),
        ]

    # A button: who may use it follows where it sits, side by side (a role in the conditions moves them into a row of
    # their own); the list of its actions follows below.
    actions = [describe_action(language, action, library) for action in draft.config.actions]
    action_list = section(
        "actions", numbered(actions, "editor.summary.no_actions"), spaced=True, listed=bool(actions), divided=True
    )
    return [*sections, conditions, action_list]


def _choice_text(language: SupportedLanguage, minimum: int, maximum: int) -> str:
    """How many options may be chosen: "1 to 3" - or, when it is exactly as many as it is at least, just that many:
    "1 option", where "1 to 1" would only be confusing."""
    if minimum == maximum:
        return t(language, "editor.summary.choice_exact", count=maximum)
    return t(language, "editor.summary.choice", minimum=minimum, maximum=maximum)


def describe_draft(
    language: SupportedLanguage, draft: ItemDraft, *, placement: str | None, library: InteractiveLibrary | None = None
) -> str:
    """The summary of a button, dropdown or form as one text: every part of it, one below the other."""
    return "\n".join(sections_text(draft_sections(language, draft, placement=placement, library=library)))


def fit_lines(lines: Sequence[str], more: Callable[[int], str], budget: int = SECTION_BUDGET) -> list[str]:
    """The lines as far as they fit the budget - each costs its length and three for its quote mark and line break.
    When some are left out, a last line says how many (`more` makes that text). A line that is too long alone is
    cut. Whole lines are kept so that a mention or code span is never cut in the middle."""

    def cost(text: str) -> int:
        """What a line takes from the budget."""
        return len(text) + 3

    if sum(cost(line) for line in lines) <= budget:
        return list(lines)

    reserve = cost(more(len(lines)))
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + cost(line) + reserve > budget:
            break
        kept.append(line)
        used += cost(line)

    if not kept:  # even the first line alone is too long
        kept = [f"{lines[0][: max(budget - reserve - 4, 1)]}…"]

    hidden = len(lines) - len(kept)
    return [*kept, more(hidden)] if hidden > 0 else kept


def section_title(section: Section) -> str:
    """The name of a part in a text: its emoji in a code span and the name in bold, followed by a colon - except after
    a question, which ends the name already. The blank character an embed field uses to be wider is not in it."""
    name = section.name.replace(BLANK_LINE, "").strip()
    colon = "" if name.endswith("?") else ":"
    return f"`{section.emoji}` ~ **{name}{colon}**"


def sections_text(sections: Sequence[Section], *, spaced: bool = True) -> list[str]:
    """The parts of a summary as lines of text: a part of one line sits behind its name, a longer one - and a list -
    is quoted below it. A spaced part has a blank line above it, unless `spaced` is off."""
    lines: list[str] = []
    for section in sections:
        if spaced and section.spaced and lines:
            lines.append("")
        title = section_title(section)
        if len(section.lines) == 1 and section.quoted and not section.listed:
            lines.append(f"{title} {section.lines[0]}")
        else:
            lines.append(title)
            lines.extend(f"> {line}" if section.quoted else line for line in section.lines)
    return lines


def section_blocks(sections: Sequence[Section]) -> list[list[Section]]:
    """The parts of a summary in the texts a text screen shows them in: a part that is `divided` starts a text of
    its own, the others join the one before."""
    blocks: list[list[Section]] = []
    for section in sections:
        if section.divided or not blocks:
            blocks.append([section])
        else:
            blocks[-1].append(section)
    return blocks


BLANK_LINE: str = "⠀"
"""A line that looks empty but stays: Discord drops ordinary blank lines at the end of an embed field."""


def section_field(section: Section) -> tuple[str, str, bool]:
    """A part of the summary as an embed field: its name with the emoji in a code span, its text quoted line by
    line, and whether it sits inline."""
    name = f"`{section.emoji}` - {section.name}"[:256]
    value = "\n".join(f"> {line}" if section.quoted else line for line in section.lines) or "> —"
    return name, value[:1024], section.inline


FILLER_FIELD: tuple[str, str, bool] = ("\u200b", "\u200b", True)
"""An empty inline field. Discord puts up to three inline fields side by side, so it fills what is left of a row to make
the next inline field start a row of its own."""
FIELDS_PER_ROW: int = 3


def _field_rows(sections: Sequence[Section]) -> list[list[int]]:
    """Which parts share a row of fields, as Discord lays them out: inline parts side by side, three at most; a part
    that is not inline has a row to itself, and a spaced part starts a new one."""
    rows: list[list[int]] = []
    for index, section in enumerate(sections):
        row_is_open = bool(rows) and len(rows[-1]) < FIELDS_PER_ROW and all(sections[i].inline for i in rows[-1])
        if section.inline and row_is_open and not section.spaced:
            rows[-1].append(index)
        else:
            rows.append([index])
    return rows


def section_fields(sections: Sequence[Section]) -> list[tuple[str, str, bool]]:
    """The parts of a summary as embed fields. A field cannot start with a blank line, so one that is `spaced` gets
    its blank line from the fields right above it: those that share the row before end with a line that stays, which
    makes that row one line taller. A row of inline fields that is not full, followed by another row of inline fields,
    is filled up with empty fields - or Discord would pull the first of the next row into it - and so is a `padded`
    row of two, so that its fields are as wide as those of the other rows that are filled up."""
    fields = [list(section_field(section)) for section in sections]
    rows = _field_rows(sections)

    for previous, row in pairwise(rows):
        if sections[row[0]].spaced:
            for position in previous:
                fields[position][1] = f"{fields[position][1]}\n{BLANK_LINE}"[:1024]

    result: list[tuple[str, str, bool]] = []
    for number, row in enumerate(rows):
        result.extend((str(fields[i][0]), str(fields[i][1]), bool(fields[i][2])) for i in row)
        following = rows[number + 1] if number + 1 < len(rows) else None
        is_inline_row = all(sections[i].inline for i in row)
        before_inline_row = following is not None and sections[following[0]].inline
        padded_pair = len(row) == 2 and any(sections[i].padded for i in row)
        if is_inline_row and len(row) < FIELDS_PER_ROW and (before_inline_row or padded_pair):
            result.extend([FILLER_FIELD] * (FIELDS_PER_ROW - len(row)))
    return result


def draft_name(language: SupportedLanguage, draft: ItemDraft, *, plain: bool = False) -> str:
    """How a button or dropdown is called in lists: its emoji and label (a dropdown: its placeholder), or a
    generic name if it has none. `plain` leaves out a custom emoji, for places that cannot show it - a dropdown
    entry or a code span."""
    if draft.is_form:
        return draft.label or t(language, "editor.unnamed_form")
    if draft.is_select:
        return draft.placeholder or t(language, f"editor.unnamed_select.{draft.mode.value}")

    emoji = None if plain and is_custom_emoji(draft.emoji) else draft.emoji
    parts: list[str] = []
    if emoji:
        parts.append(emoji)
    if draft.label:
        parts.append(draft.label)
    return " ".join(parts) if parts else t(language, "editor.unnamed")


def draft_option(
    language: SupportedLanguage, draft: ItemDraft, *, default: bool, placed: bool, place: str | None = None
) -> SelectOption:
    """The dropdown option that selects a button or dropdown in a list of the user's items. A placed one says where
    it sits (`place`, e.g. "Row 1") in front of the fact that it is placed."""
    if placed and place:
        description = t(language, "editor.option.placed_at", place=place)
    else:
        description = t(language, "editor.option.placed" if placed else "editor.option.unplaced")
    return SelectOption(
        label=draft_name(language, draft, plain=True)[:100],
        value=str(draft.id),
        description=description,
        emoji=draft_emoji(draft),
        default=default,
    )


ACTION_GROUPS: dict[str, str] = {"roles": "🎭", "message": "💬", "delete_message": "🗑️", "open_form": "📋"}
"""What the user can add to a button, by the value of its entry in the dropdown, with its emoji. Role actions and
message actions are one entry each: their screen has the type to choose from."""


def action_group_of(action_type: ActionType) -> str:
    """The entry of `ACTION_GROUPS` an action type belongs to."""
    if action_type in ROLE_ACTIONS:
        return "roles"
    if action_type in MESSAGE_ACTIONS:
        return "message"
    return action_type.value


def action_group_options(language: SupportedLanguage, exclude: Collection[str] = ()) -> list[SelectOption]:
    """The dropdown options to add an action: roles, a message, deleting the message, opening a form - except the
    excluded groups (a form cannot open another form)."""
    options: list[SelectOption] = []
    for group, emoji in ACTION_GROUPS.items():
        if group in exclude:
            continue
        own = group in ("roles", "message")
        options.append(
            SelectOption(
                label=t(language, f"editor.action_group.{group}.label" if own else f"editor.action_name.{group}"),
                description=t(
                    language, f"editor.action_group.{group}.description" if own else f"editor.action_help.{group}"
                ),
                value=group,
                emoji=emoji,
            )
        )
    return options


def action_name(language: SupportedLanguage, action_type: ActionType, roles: int = 0) -> str:
    """The name of an action type. A role action speaks of one role or of several, depending on how many (`roles`) it
    has - none yet counts as several."""
    return t(language, f"editor.action_name.{action_type.value}", count=roles)


def action_help(language: SupportedLanguage, action_type: ActionType, roles: int = 0) -> str:
    """What an action type does, worded for one role or for several as `action_name` is."""
    return t(language, f"editor.action_help.{action_type.value}", count=roles)


def action_type_options(language: SupportedLanguage, exclude: Collection[ActionType] = ()) -> list[SelectOption]:
    """The dropdown options to add an action: one per action type, except the excluded ones (a form cannot open
    another form)."""
    return [
        SelectOption(
            label=action_name(language, action_type),
            description=action_help(language, action_type),
            value=action_type.value,
            emoji=ACTION_EMOJIS[action_type],
        )
        for action_type in ActionType
        if action_type not in exclude
    ]


def condition_type_options(language: SupportedLanguage, used: Collection[ConditionType]) -> list[SelectOption]:
    """The dropdown options to add a restriction: one per type that the item does not have yet."""
    return [
        SelectOption(
            label=t(language, f"editor.condition_name.{condition_type.value}"),
            description=t(language, f"editor.condition_help.{condition_type.value}"),
            value=condition_type.value,
            emoji=CONDITION_EMOJIS[condition_type],
        )
        for condition_type in ConditionType
        if condition_type not in used
    ]


def problem_text(language: SupportedLanguage, problem: ConfigProblem, *, count: int = 0, **variables: Any) -> str:
    """The explanation for why a configuration cannot be saved. The limits a text may mention are filled in. A text
    about roles speaks of one role or several depending on `count` (none counts as several)."""
    limits = {"max": MAX_ACTIONS_PER_ITEM, "max_conditions": MAX_CONDITIONS_PER_ITEM, "roles": ""}
    return t(language, f"editor.problems.{problem.value}", count=count, **{**limits, **variables})


def conflict_text(
    language: SupportedLanguage,
    problem: ConfigProblem,
    *,
    actions: Sequence[Action] = (),
    conditions: Sequence[Condition] = (),
) -> str:
    """The explanation for a problem between the `actions` and `conditions` of an item. When roles are the cause - used
    twice, required and blocked, changed to no effect - they are named."""
    if problem is ConfigProblem.CONFLICTING_ROLE_ACTIONS:
        roles = clashing_action_roles(actions)
    elif problem is ConfigProblem.CONFLICTING_ROLES:
        roles = conflicting_roles(conditions)
    else:
        roles = needless_role_changes(actions, conditions).get(problem, [])
    return problem_text(language, problem, count=len(roles), roles=", ".join(f"<@&{role_id}>" for role_id in roles))
