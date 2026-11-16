from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from core.discord_api.limits import (
    MAX_MESSAGE_CONTENT,
    MAX_MODAL_TEXTINPUT,
    MAX_MODAL_TEXTINPUT_PLACEHOLDER,
    MAX_MODAL_TITLE,
    MAX_SELECT_ITEMS,
)

# Limits that are ours, not Discord's (Discord's own limits live in `core.discord_api.limits`).
MAX_ACTIONS_PER_ITEM: int = 5
"""Actions a single button, dropdown option or form may run."""
MAX_ROLES_PER_ACTION: int = 10
"""Roles one role action may touch - several roles in one action keeps the action list short."""
MAX_CONDITION_ROLES: int = 10
MAX_ACCOUNT_AGE_DAYS: int = 3650
MAX_COOLDOWN_SECONDS: int = 3600
MAX_QUESTIONS_PER_FORM: int = 5
"""Discord shows at most five fields in one form (modal)."""
MAX_QUESTION_LABEL: int = 45

INTERACTIVE_EMOJI: str = "🎯"
"""The emoji of the "Buttons & Dropdowns" entry in the main menu and of its screen, in both builders."""

CONFIG_VERSION: int = 1

MAX_CONDITIONS_PER_ITEM: int = 3
"""Conditions a single button, dropdown, dropdown option or form may have."""

# The permissions that only moderators have. An item that deletes its message has to be limited to people with
# one of these (or to a role), as it could otherwise be used by everybody.
MODERATOR_PERMISSIONS: tuple[str, ...] = (
    "manage_messages",
    "kick_members",
    "ban_members",
    "moderate_members",
    "manage_guild",
    "administrator",
)

# The permissions a "has permissions" condition can ask for - any one of them is enough. These are the ones
# servers commonly tie to roles: running the server, moderating, and what members may do in a channel.
CONDITION_PERMISSIONS: tuple[str, ...] = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_messages",
    "manage_webhooks",
    "manage_nicknames",
    "manage_threads",
    "manage_events",
    "manage_expressions",
    "kick_members",
    "ban_members",
    "moderate_members",
    "mention_everyone",
    "view_audit_log",
    "mute_members",
    "deafen_members",
    "move_members",
    "create_instant_invite",
    "change_nickname",
    "send_messages",
    "embed_links",
    "attach_files",
    "add_reactions",
)


class ItemKind(StrEnum):
    """What an interactive item is, as stored."""

    BUTTON = "button"
    SELECT = "select"
    FORM = "form"


class ActionType(StrEnum):
    """Everything a click can do.

    # TODO(tickets): add `CREATE_TICKET` once the internal ticket system exists.
    """

    ROLE_ADD = "role_add"
    ROLE_REMOVE = "role_remove"
    ROLE_TOGGLE = "role_toggle"
    ROLE_SET = "role_set"
    REPLY = "reply"
    DM_USER = "dm_user"
    SEND_CHANNEL = "send_channel"
    DELETE_MESSAGE = "delete_message"
    OPEN_FORM = "open_form"


ROLE_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.ROLE_ADD, ActionType.ROLE_REMOVE, ActionType.ROLE_TOGGLE, ActionType.ROLE_SET}
)
MESSAGE_ACTIONS: frozenset[ActionType] = frozenset({ActionType.REPLY, ActionType.DM_USER, ActionType.SEND_CHANNEL})
"""The actions that send a message and therefore carry a `MessagePayload`."""


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """Static rules of an action type that the editor and the validation share.

    `responds` marks actions that answer the interaction themselves (a reply or a form), of which an
    item may have at most one. `unique` marks actions that make no sense more than once per item.
    """

    responds: bool = False
    unique: bool = False


ACTION_SPECS: dict[ActionType, ActionSpec] = {action_type: ActionSpec() for action_type in ActionType}
ACTION_SPECS[ActionType.REPLY] = ActionSpec(responds=True)
ACTION_SPECS[ActionType.DELETE_MESSAGE] = ActionSpec(unique=True)
ACTION_SPECS[ActionType.OPEN_FORM] = ActionSpec(responds=True, unique=True)


class ConditionType(StrEnum):
    """Everything that can restrict who may use an item."""

    ROLE_REQUIRED = "role_required"
    ROLE_FORBIDDEN = "role_forbidden"
    PERMISSIONS = "permissions"
    ACCOUNT_AGE = "account_age"
    MEMBER_AGE = "member_age"
    ONCE_PER_USER = "once_per_user"
    COOLDOWN = "cooldown"


ROLE_CONDITIONS: frozenset[ConditionType] = frozenset({ConditionType.ROLE_REQUIRED, ConditionType.ROLE_FORBIDDEN})


class ConfigProblem(StrEnum):
    """Why an `ItemConfig` cannot be saved. The values double as locale keys of the editor."""

    TOO_MANY_ACTIONS = "too_many_actions"
    TOO_MANY_CONDITIONS = "too_many_conditions"
    CONFLICTING_ROLES = "conflicting_roles"
    ACTION_WITHOUT_ROLES = "action_without_roles"
    TOO_MANY_ROLES = "too_many_roles"
    TOO_MANY_RESPONDING_ACTIONS = "too_many_responding_actions"
    DUPLICATE_ACTION = "duplicate_action"
    CONFLICTING_ROLE_ACTIONS = "conflicting_role_actions"
    SET_NOT_ALONE = "set_not_alone"
    ADDS_REQUIRED_ROLE = "adds_required_role"
    REMOVES_FORBIDDEN_ROLE = "removes_forbidden_role"
    DUPLICATE_CONDITION = "duplicate_condition"
    CONDITION_WITHOUT_ROLES = "condition_without_roles"
    CONDITION_WITHOUT_PERMISSIONS = "condition_without_permissions"
    CONDITION_INVALID_AMOUNT = "condition_invalid_amount"
    PAYLOAD_EMPTY = "payload_empty"
    CHANNEL_MISSING = "channel_missing"
    DELETE_WITHOUT_RESTRICTION = "delete_without_restriction"
    TOO_MANY_OPTIONS = "too_many_options"
    OPTION_WITHOUT_ROLE = "option_without_role"
    INVALID_SELECTION_RANGE = "invalid_selection_range"
    FORM_MISSING = "form_missing"
    FORM_NOT_ALONE = "form_not_alone"
    FORM_OPENER_ONCE = "form_opener_once"
    NESTED_FORM = "nested_form"
    NO_QUESTIONS = "no_questions"
    TOO_MANY_QUESTIONS = "too_many_questions"
    INVALID_QUESTION = "invalid_question"


def _int_tuple(value: object) -> tuple[int, ...]:
    """The distinct ints of a stored list in order; anything else in it (or a non-list) is dropped."""
    if not isinstance(value, list):
        return ()

    seen: dict[int, None] = {}
    for entry in value:
        if isinstance(entry, int) and not isinstance(entry, bool):
            seen[entry] = None
    return tuple(seen)


class PayloadKind(StrEnum):
    """What a message action sends: plain text, or a snapshot of one of the user's saved templates."""

    TEXT = "text"
    EMBED = "embed"
    CONTAINER = "container"


@dataclass(frozen=True, slots=True)
class MessagePayload:
    """The message an action sends.

    A `TEXT` payload is just `text` (with placeholders such as `{user}`). The other kinds are a *snapshot* of a
    saved template taken when the action was configured: `data` is the template's stored payload (embed dicts or
    component nodes), so the action keeps working - unchanged - even if the template is edited or deleted later.
    """

    text: str = ""
    kind: PayloadKind = PayloadKind.TEXT
    template_name: str | None = None
    data: list[dict[str, object]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to send."""
        if self.kind is PayloadKind.TEXT:
            return not self.text.strip()
        return not self.data

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        data: dict[str, object] = {"kind": self.kind.value, "text": self.text}
        if self.kind is not PayloadKind.TEXT:
            data["template_name"] = self.template_name
            data["data"] = self.data
        return data

    @classmethod
    def from_data(cls, data: object) -> MessagePayload | None:
        """Rebuild a payload from its stored form, or `None` if it is unusable."""
        if not isinstance(data, dict):
            return None

        raw_kind = data.get("kind")
        if not isinstance(raw_kind, str) or raw_kind not in PayloadKind:
            return None

        text = data.get("text")
        name = data.get("template_name")
        stored = data.get("data")
        return cls(
            text=text[:MAX_MESSAGE_CONTENT] if isinstance(text, str) else "",
            kind=PayloadKind(raw_kind),
            template_name=name if isinstance(name, str) else None,
            data=[dict(entry) for entry in stored if isinstance(entry, dict)] if isinstance(stored, list) else [],
        )


@dataclass(frozen=True, slots=True)
class Action:
    """One step of an item. Which fields matter depends on `type`."""

    type: ActionType
    roles: tuple[int, ...] = ()
    payload: MessagePayload | None = None
    """The message of `REPLY`, `DM_USER` and `SEND_CHANNEL`."""
    channel_id: int | None = None
    """`SEND_CHANNEL` only: where the message goes."""
    form_id: int | None = None
    """`OPEN_FORM` only: the form to open. In the builder this is the id of the form's draft, once stored the id
    of its database row."""

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        data: dict[str, object] = {"type": self.type.value}
        if self.type in ROLE_ACTIONS:
            data["roles"] = list(self.roles)
        if self.type in MESSAGE_ACTIONS and self.payload is not None:
            data["payload"] = self.payload.to_data()
        if self.type is ActionType.SEND_CHANNEL:
            data["channel_id"] = self.channel_id
        if self.type is ActionType.OPEN_FORM:
            data["form_id"] = self.form_id
        return data

    @classmethod
    def from_data(cls, data: object) -> Action | None:
        """Rebuild an action from its stored form, or `None` if it is unusable (e.g. a type that was removed)."""
        if not isinstance(data, dict):
            return None

        raw_type = data.get("type")
        if not isinstance(raw_type, str) or raw_type not in ActionType:
            return None
        action_type = ActionType(raw_type)

        payload = MessagePayload.from_data(data.get("payload")) if action_type in MESSAGE_ACTIONS else None
        channel_id, form_id = data.get("channel_id"), data.get("form_id")
        return cls(
            type=action_type,
            roles=_int_tuple(data.get("roles")),
            payload=payload,
            channel_id=channel_id if isinstance(channel_id, int) and not isinstance(channel_id, bool) else None,
            form_id=form_id if isinstance(form_id, int) and not isinstance(form_id, bool) else None,
        )


@dataclass(frozen=True, slots=True)
class Condition:
    """One restriction on who may use an item. Which fields matter depends on `type`."""

    type: ConditionType
    roles: tuple[int, ...] = ()
    match_all: bool = False
    """`ROLE_REQUIRED` only: whether all roles are needed instead of any one of them."""
    permissions: tuple[str, ...] = ()
    amount: int = 0
    """Days for `ACCOUNT_AGE` and `MEMBER_AGE`, seconds for `COOLDOWN`."""

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        data: dict[str, object] = {"type": self.type.value}
        if self.type in ROLE_CONDITIONS:
            data["roles"] = list(self.roles)
        if self.type is ConditionType.ROLE_REQUIRED:
            data["match_all"] = self.match_all
        if self.type is ConditionType.PERMISSIONS:
            data["permissions"] = list(self.permissions)
        if self.type in (ConditionType.ACCOUNT_AGE, ConditionType.MEMBER_AGE, ConditionType.COOLDOWN):
            data["amount"] = self.amount
        return data

    @classmethod
    def from_data(cls, data: object) -> Condition | None:
        """Rebuild a condition from its stored form, or `None` if it is unusable."""
        if not isinstance(data, dict):
            return None

        raw_type = data.get("type")
        if not isinstance(raw_type, str) or raw_type not in ConditionType:
            return None
        condition_type = ConditionType(raw_type)

        permissions = data.get("permissions")
        amount = data.get("amount")
        return cls(
            type=condition_type,
            roles=_int_tuple(data.get("roles")),
            match_all=data.get("match_all") is True,
            permissions=tuple(name for name in permissions if isinstance(name, str))
            if isinstance(permissions, list)
            else (),
            amount=amount if isinstance(amount, int) and not isinstance(amount, bool) else 0,
        )


@dataclass(slots=True)
class ItemConfig:
    """What an item does (`actions`, run in order) and who may use it (`conditions`, all must hold)."""

    actions: list[Action] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        return {
            "version": CONFIG_VERSION,
            "actions": [action.to_data() for action in self.actions],
            "conditions": [condition.to_data() for condition in self.conditions],
        }

    @classmethod
    def from_data(cls, data: object) -> ItemConfig:
        """Rebuild a config from its stored form, dropping whatever is unusable instead of failing the click."""
        if not isinstance(data, dict):
            return cls()

        raw_actions, raw_conditions = data.get("actions"), data.get("conditions")
        actions = [Action.from_data(entry) for entry in raw_actions] if isinstance(raw_actions, list) else []
        conditions = [Condition.from_data(entry) for entry in raw_conditions] if isinstance(raw_conditions, list) else []
        return cls(
            actions=[action for action in actions if action is not None],
            conditions=[condition for condition in conditions if condition is not None],
        )


def _validate_action(action: Action) -> list[ConfigProblem]:
    """Problems of a single action, independent of its siblings."""
    problems: list[ConfigProblem] = []
    if action.type in ROLE_ACTIONS and not action.roles:
        problems.append(ConfigProblem.ACTION_WITHOUT_ROLES)
    if len(action.roles) > MAX_ROLES_PER_ACTION:
        problems.append(ConfigProblem.TOO_MANY_ROLES)
    if action.type in MESSAGE_ACTIONS and (action.payload is None or action.payload.is_empty):
        problems.append(ConfigProblem.PAYLOAD_EMPTY)
    if action.type is ActionType.SEND_CHANNEL and action.channel_id is None:
        problems.append(ConfigProblem.CHANNEL_MISSING)
    if action.type is ActionType.OPEN_FORM and action.form_id is None:
        problems.append(ConfigProblem.FORM_MISSING)
    return problems


def clashing_action_roles(actions: Sequence[Action]) -> list[int]:
    """The roles that more than one role action changes, in order. Each role belongs to one action only: the actions
    are applied one after the other, so two of them on the same role would cancel or repeat each other."""
    counts: dict[int, int] = {}
    for action in actions:
        if action.type in ROLE_ACTIONS:
            for role_id in action.roles:
                counts[role_id] = counts.get(role_id, 0) + 1
    return [role_id for role_id, count in counts.items() if count > 1]


def action_conflicts(actions: Sequence[Action]) -> list[ConfigProblem]:
    """The ways the actions contradict or repeat each other, each listed once. Whether every action is complete is
    another matter - see `validate_config`.

    The role actions are applied one after the other to the same roles. So they must not overlap: a role that one
    action adds and another removes would end up as the order happens to leave it. And "set role" decides every role
    of the user, so no other role action can stand next to it. Of the other actions an item may answer only once,
    must not repeat what cannot be done twice (deleting the message, opening a form) and must not send the very same
    message twice.
    """
    problems: dict[ConfigProblem, None] = {}

    if sum(ACTION_SPECS[action.type].responds for action in actions) > 1:
        problems[ConfigProblem.TOO_MANY_RESPONDING_ACTIONS] = None

    unique_types = [action.type for action in actions if ACTION_SPECS[action.type].unique]
    messages = [action for action in actions if action.type in MESSAGE_ACTIONS]
    repeated = any(message == other for position, message in enumerate(messages) for other in messages[position + 1 :])
    if len(unique_types) != len(set(unique_types)) or repeated:
        problems[ConfigProblem.DUPLICATE_ACTION] = None

    role_actions = [action for action in actions if action.type in ROLE_ACTIONS]
    if len(role_actions) > 1 and any(action.type is ActionType.ROLE_SET for action in role_actions):
        problems[ConfigProblem.SET_NOT_ALONE] = None
    if clashing_action_roles(actions):
        problems[ConfigProblem.CONFLICTING_ROLE_ACTIONS] = None

    return list(problems)


def needless_role_changes(actions: Sequence[Action], conditions: Sequence[Condition]) -> dict[ConfigProblem, list[int]]:
    """The role changes the conditions make pointless, by problem and in order: roles that are added although everybody
    allowed to click has them already (`ADDS_REQUIRED_ROLE`), and roles that are removed although nobody allowed to
    click has them (`REMOVES_FORBIDDEN_ROLE`). Toggling still changes something, so it is not judged.

    A role is certainly held if it is required on its own or together with all the others (`match_all`) - with
    "any of these" a member may hold another one instead. A blocked role is never held, whatever else is set.
    """
    held = {
        role_id
        for condition in conditions
        if condition.type is ConditionType.ROLE_REQUIRED and (condition.match_all or len(condition.roles) == 1)
        for role_id in condition.roles
    }
    barred = {
        role_id for condition in conditions if condition.type is ConditionType.ROLE_FORBIDDEN for role_id in condition.roles
    }
    added = [role_id for action in actions if action.type is ActionType.ROLE_ADD for role_id in action.roles]
    removed = [role_id for action in actions if action.type is ActionType.ROLE_REMOVE for role_id in action.roles]

    found: dict[ConfigProblem, list[int]] = {}
    if pointless_adds := list(dict.fromkeys(role_id for role_id in added if role_id in held)):
        found[ConfigProblem.ADDS_REQUIRED_ROLE] = pointless_adds
    if pointless_removes := list(dict.fromkeys(role_id for role_id in removed if role_id in barred)):
        found[ConfigProblem.REMOVES_FORBIDDEN_ROLE] = pointless_removes
    return found


def condition_conflicts(actions: Sequence[Action], conditions: Sequence[Condition]) -> list[ConfigProblem]:
    """The ways the actions contradict the conditions that decide who may trigger them, each listed once. Pass every
    condition that applies: the item's own and, for the option of a dropdown, those of the dropdown."""
    return list(needless_role_changes(actions, conditions))


def conflicting_roles(conditions: Sequence[Condition]) -> list[int]:
    """The roles that the conditions both require and forbid - nobody could satisfy that. Conditions of a dropdown
    and of its option belong together, so pass both."""
    required = {
        role for condition in conditions if condition.type is ConditionType.ROLE_REQUIRED for role in condition.roles
    }
    clashes = [
        role
        for condition in conditions
        if condition.type is ConditionType.ROLE_FORBIDDEN
        for role in condition.roles
        if role in required
    ]
    return list(dict.fromkeys(clashes))


def is_restricted(conditions: Sequence[Condition]) -> bool:
    """Whether the conditions limit use to chosen people (a role or moderator permissions) - which an item that
    deletes the message needs, as otherwise everybody could delete it. Permissions only count when all of the
    chosen ones are a moderator's: one that every member has would let everybody through."""
    return any(
        condition.type is ConditionType.ROLE_REQUIRED
        or (
            condition.type is ConditionType.PERMISSIONS
            and bool(condition.permissions)
            and all(name in MODERATOR_PERMISSIONS for name in condition.permissions)
        )
        for condition in conditions
    )


def _validate_condition(condition: Condition) -> list[ConfigProblem]:
    """Problems of a single condition, independent of its siblings."""
    if condition.type in ROLE_CONDITIONS:
        if not condition.roles:
            return [ConfigProblem.CONDITION_WITHOUT_ROLES]
        return [ConfigProblem.TOO_MANY_ROLES] if len(condition.roles) > MAX_CONDITION_ROLES else []

    if condition.type is ConditionType.PERMISSIONS:
        valid = bool(condition.permissions) and all(name in CONDITION_PERMISSIONS for name in condition.permissions)
        return [] if valid else [ConfigProblem.CONDITION_WITHOUT_PERMISSIONS]

    limits = {
        ConditionType.ACCOUNT_AGE: MAX_ACCOUNT_AGE_DAYS,
        ConditionType.MEMBER_AGE: MAX_ACCOUNT_AGE_DAYS,
        ConditionType.COOLDOWN: MAX_COOLDOWN_SECONDS,
    }
    if condition.type in limits and not 1 <= condition.amount <= limits[condition.type]:
        return [ConfigProblem.CONDITION_INVALID_AMOUNT]
    return []


def validate_config(
    config: ItemConfig, *, inherited: Sequence[Condition] = (), in_form: bool = False
) -> list[ConfigProblem]:
    """Every reason `config` must not be saved as it is (each problem listed once); empty if it is fine.

    `inherited` are the conditions of the dropdown the config belongs to (for an option), which count
    towards the restriction a "delete message" action needs. `in_form` marks the actions a form runs
    once it is submitted.
    """
    problems: dict[ConfigProblem, None] = {}

    if len(config.actions) > MAX_ACTIONS_PER_ITEM:
        problems[ConfigProblem.TOO_MANY_ACTIONS] = None
    if len(config.conditions) > MAX_CONDITIONS_PER_ITEM:
        problems[ConfigProblem.TOO_MANY_CONDITIONS] = None

    for action in config.actions:
        for problem in _validate_action(action):
            problems[problem] = None

    for problem in action_conflicts(config.actions):
        problems[problem] = None
    for problem in condition_conflicts(config.actions, [*config.conditions, *inherited]):
        problems[problem] = None

    if any(action.type is ActionType.DELETE_MESSAGE for action in config.actions) and not is_restricted(
        [*config.conditions, *inherited]
    ):
        problems[ConfigProblem.DELETE_WITHOUT_RESTRICTION] = None

    if any(action.type is ActionType.OPEN_FORM for action in config.actions):
        # A form needs the first answer to the click (a modal), so it can neither be combined with other actions
        # nor open another form; what should happen is set on the form itself - and so is "once per person".
        if in_form:
            problems[ConfigProblem.NESTED_FORM] = None
        if len(config.actions) > 1:
            problems[ConfigProblem.FORM_NOT_ALONE] = None
        if any(condition.type is ConditionType.ONCE_PER_USER for condition in [*config.conditions, *inherited]):
            problems[ConfigProblem.FORM_OPENER_ONCE] = None

    condition_types = [condition.type for condition in config.conditions]
    if len(condition_types) != len(set(condition_types)):
        problems[ConfigProblem.DUPLICATE_CONDITION] = None

    if conflicting_roles([*config.conditions, *inherited]):
        problems[ConfigProblem.CONFLICTING_ROLES] = None

    for condition in config.conditions:
        for problem in _validate_condition(condition):
            problems[problem] = None

    return list(problems)


class SelectMode(StrEnum):
    """How a dropdown works: every option runs its own actions, or the options are roles and the selection is synced."""

    STRINGS = "strings"
    ROLES = "roles"


@dataclass(slots=True)
class OptionConfig:
    """What one option of a dropdown does. In `ROLES` mode the option stands for `role_id` and has no actions."""

    key: str
    """The option's value in the dropdown - what Discord reports back when it is selected."""
    config: ItemConfig = field(default_factory=ItemConfig)
    role_id: int | None = None

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        data = self.config.to_data()
        data["key"] = self.key
        data["role_id"] = self.role_id
        return data

    @classmethod
    def from_data(cls, data: object) -> OptionConfig | None:
        """Rebuild an option from its stored form, or `None` if it is unusable."""
        if not isinstance(data, dict):
            return None

        key = data.get("key")
        role_id = data.get("role_id")
        if not isinstance(key, str) or not key:
            return None
        return cls(
            key=key,
            config=ItemConfig.from_data(data),
            role_id=role_id if isinstance(role_id, int) and not isinstance(role_id, bool) else None,
        )


@dataclass(slots=True)
class SelectConfig:
    """What a dropdown does (per option) and who may use it (`conditions`, valid for every option)."""

    mode: SelectMode = SelectMode.STRINGS
    conditions: list[Condition] = field(default_factory=list)
    options: list[OptionConfig] = field(default_factory=list)

    def option(self, key: str) -> OptionConfig | None:
        """The option with this key, or `None`."""
        return next((option for option in self.options if option.key == key), None)

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        return {
            "version": CONFIG_VERSION,
            "mode": self.mode.value,
            "conditions": [condition.to_data() for condition in self.conditions],
            "options": [option.to_data() for option in self.options],
        }

    @classmethod
    def from_data(cls, data: object) -> SelectConfig:
        """Rebuild a dropdown config from its stored form, dropping whatever is unusable."""
        if not isinstance(data, dict):
            return cls()

        raw_mode = data.get("mode")
        raw_conditions, raw_options = data.get("conditions"), data.get("options")
        conditions = [Condition.from_data(entry) for entry in raw_conditions] if isinstance(raw_conditions, list) else []
        options = [OptionConfig.from_data(entry) for entry in raw_options] if isinstance(raw_options, list) else []
        return cls(
            mode=SelectMode(raw_mode) if isinstance(raw_mode, str) and raw_mode in SelectMode else SelectMode.STRINGS,
            conditions=[condition for condition in conditions if condition is not None],
            options=[option for option in options if option is not None],
        )


def validate_select_config(select: SelectConfig) -> list[ConfigProblem]:
    """Every reason a dropdown's configuration must not be saved as it is; empty if it is fine."""
    problems: dict[ConfigProblem, None] = {}

    if len(select.options) > MAX_SELECT_ITEMS:
        problems[ConfigProblem.TOO_MANY_OPTIONS] = None

    for problem in validate_config(ItemConfig(conditions=select.conditions)):
        problems[problem] = None

    for option in select.options:
        if select.mode is SelectMode.ROLES:
            if option.role_id is None:
                problems[ConfigProblem.OPTION_WITHOUT_ROLE] = None
            continue
        for problem in validate_config(option.config, inherited=select.conditions):
            problems[problem] = None

    return list(problems)


@dataclass(slots=True)
class Question:
    """One field of a form."""

    label: str
    placeholder: str | None = None
    paragraph: bool = False
    """Whether the answer is a longer text (several lines) instead of a single line."""
    required: bool = True
    min_length: int = 0
    max_length: int = MAX_MODAL_TEXTINPUT

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        return {
            "label": self.label,
            "placeholder": self.placeholder,
            "paragraph": self.paragraph,
            "required": self.required,
            "min_length": self.min_length,
            "max_length": self.max_length,
        }

    @classmethod
    def from_data(cls, data: object) -> Question | None:
        """Rebuild a question from its stored form, or `None` if it is unusable."""
        if not isinstance(data, dict):
            return None

        label, placeholder = data.get("label"), data.get("placeholder")
        minimum, maximum = data.get("min_length"), data.get("max_length")
        if not isinstance(label, str) or not label.strip():
            return None
        return cls(
            label=label[:MAX_QUESTION_LABEL],
            placeholder=placeholder[:MAX_MODAL_TEXTINPUT_PLACEHOLDER]
            if isinstance(placeholder, str) and placeholder
            else None,
            paragraph=data.get("paragraph") is True,
            required=data.get("required") is not False,
            min_length=minimum if isinstance(minimum, int) and not isinstance(minimum, bool) and minimum >= 0 else 0,
            max_length=maximum
            if isinstance(maximum, int) and not isinstance(maximum, bool) and 1 <= maximum <= MAX_MODAL_TEXTINPUT
            else MAX_MODAL_TEXTINPUT,
        )


@dataclass(slots=True)
class FormConfig:
    """A form: its title, its questions, what happens once it is submitted (`actions`) and who may use it."""

    title: str = ""
    questions: list[Question] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)

    def to_data(self) -> dict[str, object]:
        """The JSON-able form stored in the database."""
        return {
            "version": CONFIG_VERSION,
            "title": self.title,
            "questions": [question.to_data() for question in self.questions],
            "actions": [action.to_data() for action in self.actions],
            "conditions": [condition.to_data() for condition in self.conditions],
        }

    @classmethod
    def from_data(cls, data: object) -> FormConfig:
        """Rebuild a form from its stored form, dropping whatever is unusable instead of failing the click."""
        if not isinstance(data, dict):
            return cls()

        title, raw_questions = data.get("title"), data.get("questions")
        questions = [Question.from_data(entry) for entry in raw_questions] if isinstance(raw_questions, list) else []
        config = ItemConfig.from_data(data)
        return cls(
            title=title[:MAX_MODAL_TITLE] if isinstance(title, str) else "",
            questions=[question for question in questions if question is not None][:MAX_QUESTIONS_PER_FORM],
            actions=config.actions,
            conditions=config.conditions,
        )


def validate_question(question: Question) -> bool:
    """Whether a question fits what Discord allows for a form field."""
    return (
        0 < len(question.label) <= MAX_QUESTION_LABEL
        and (question.placeholder is None or len(question.placeholder) <= MAX_MODAL_TEXTINPUT_PLACEHOLDER)
        and 0 <= question.min_length <= question.max_length <= MAX_MODAL_TEXTINPUT
        and question.max_length >= 1
    )


def validate_form_config(form: FormConfig) -> list[ConfigProblem]:
    """Every reason a form must not be saved or sent as it is; empty if it is fine."""
    problems: dict[ConfigProblem, None] = {}

    if not form.questions:
        problems[ConfigProblem.NO_QUESTIONS] = None
    if len(form.questions) > MAX_QUESTIONS_PER_FORM:
        problems[ConfigProblem.TOO_MANY_QUESTIONS] = None
    if not form.title.strip() or len(form.title) > MAX_MODAL_TITLE or not all(map(validate_question, form.questions)):
        problems[ConfigProblem.INVALID_QUESTION] = None

    for problem in validate_config(ItemConfig(actions=form.actions, conditions=form.conditions), in_form=True):
        problems[problem] = None
    return list(problems)
