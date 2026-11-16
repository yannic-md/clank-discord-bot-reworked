from collections.abc import Callable, Sequence
from dataclasses import replace

from discord import Guild, Member, Role, SelectDefaultValue, SelectDefaultValueType, SelectOption, Thread
from discord.abc import GuildChannel
from discord.ui import ChannelSelect, RoleSelect

from core.enums.language import SupportedLanguage
from features.misc.builder.channels import TARGET_CHANNEL_TYPES
from features.misc.builder.interactive.editor import (
    ACTION_EMOJIS,
    Section,
    action_help,
    action_name,
    conflict_text,
    fit_lines,
    problem_text,
)
from features.misc.builder.interactive.messages import role_problem_text, t
from features.misc.builder.interactive.models import (
    MAX_ACTIONS_PER_ITEM,
    MAX_ROLES_PER_ACTION,
    ROLE_ACTIONS,
    Action,
    ActionType,
    Condition,
    ConfigProblem,
    ItemConfig,
    MessagePayload,
    PayloadKind,
    action_conflicts,
    condition_conflicts,
    validate_config,
)
from features.misc.builder.interactive.roles import role_problem
from features.misc.builder.interactive.variables import FORM_VARIABLES, VARIABLES, render_variables

ROLE_TYPES: tuple[ActionType, ...] = (
    ActionType.ROLE_ADD,
    ActionType.ROLE_REMOVE,
    ActionType.ROLE_TOGGLE,
    ActionType.ROLE_SET,
)
MESSAGE_TYPES: tuple[ActionType, ...] = (ActionType.REPLY, ActionType.DM_USER, ActionType.SEND_CHANNEL)

ROLE_SECTION_EMOJIS: dict[str, str] = {"type": "🎯", "roles": "🎭"}
MESSAGE_SECTION_EMOJIS: dict[str, str] = {"type": "🎯", "message": "💬", "channel": "📢"}


def with_type(action: Action, action_type: ActionType) -> Action:
    """The action turned into another type of the same kind. It keeps what the new type can use - the roles, the
    message - and drops the rest: the channel belongs to "channel message"."""
    if action_type in ROLE_ACTIONS:
        return replace(action, type=action_type)

    return replace(
        action, type=action_type, channel_id=action.channel_id if action_type is ActionType.SEND_CHANNEL else None
    )


def type_options(
    language: SupportedLanguage, types: Sequence[ActionType], current: ActionType, roles: int = 0
) -> list[SelectOption]:
    """The dropdown entries that let the user pick the type of an action: its name, what it does, its emoji. The role
    types speak of one role when exactly one (`roles`) is chosen, otherwise of several."""
    return [
        SelectOption(
            label=action_name(language, action_type, roles),
            description=action_help(language, action_type, roles),
            value=action_type.value,
            emoji=ACTION_EMOJIS[action_type],
            default=action_type is current,
        )
        for action_type in types
    ]


def adding_problem(language: SupportedLanguage, config: ItemConfig, group: str = "") -> str | None:
    """Why another action cannot be added to the config - a form must be the only action, "set role" the only role
    action (for the `roles` group), and there is a limit - or `None`."""
    if any(action.type is ActionType.OPEN_FORM for action in config.actions):
        return problem_text(language, ConfigProblem.FORM_NOT_ALONE)

    if len(config.actions) >= MAX_ACTIONS_PER_ITEM:
        return problem_text(language, ConfigProblem.TOO_MANY_ACTIONS)

    if group == "roles" and any(action.type is ActionType.ROLE_SET for action in config.actions):
        return problem_text(language, ConfigProblem.SET_NOT_ALONE)

    return None


def new_message_action(language: SupportedLanguage, config: ItemConfig) -> Action:
    """The message action a new screen starts with: a reply - unless the item replies already, as it can only answer
    once - then a direct message. Its text is an example that uses some of the variables, so that they can be seen
    at work and the message is not empty."""
    replies = any(action.type is ActionType.REPLY for action in config.actions)
    payload = MessagePayload(t(language, "action_screen.message.default_text"))
    return Action(ActionType.DM_USER if replies else ActionType.REPLY, payload=payload)


def clash_problem(
    language: SupportedLanguage,
    config: ItemConfig,
    index: int | None,
    action: Action,
    inherited: Sequence[Condition] = (),
) -> str | None:
    """Why `action` - the one at `index` of the item, or a new one - cannot stand next to the item's other actions
    or contradicts its conditions (`inherited` are those of the dropdown an option belongs to), or `None`. Only the
    rules between these count (a role in two actions, "set role" next to other role actions, a second reply, a role
    added that the conditions require ...); whether the action is complete is checked when it is saved. What the
    others got wrong among themselves is not blamed on this one."""
    others = [other for position, other in enumerate(config.actions) if position != index]
    conditions = [*config.conditions, *inherited]
    known = {*action_conflicts(others), *condition_conflicts(others, conditions)}
    actions = [*others, action]
    for problem in [*action_conflicts(actions), *condition_conflicts(actions, conditions)]:
        if problem not in known:
            return conflict_text(language, problem, actions=actions, conditions=conditions)

    return None


def save_action(
    language: SupportedLanguage,
    config: ItemConfig,
    inherited: Sequence[Condition],
    index: int | None,
    action: Action,
    *,
    in_form: bool,
) -> str | None:
    """Store the action as a new one (`index` is `None`) or in place of the one at `index`. Returns the reason, and
    stores nothing, if the item would not be valid with it."""
    actions = list(config.actions)
    if index is None:
        actions.append(action)
    else:
        actions[index] = action

    problems = validate_config(replace(config, actions=actions), inherited=inherited, in_form=in_form)
    if problems:
        return conflict_text(language, problems[0], actions=actions, conditions=[*config.conditions, *inherited])

    config.actions[:] = actions
    return None


def with_roles(action: Action, role_ids: Sequence[int]) -> Action:
    """The role action with other roles."""
    return replace(action, roles=tuple(dict.fromkeys(role_ids)))


def chosen_role_problem(language: SupportedLanguage, roles: Sequence[Role], creator: Member, guild: Guild) -> str | None:
    """Why a role cannot be picked, or `None`: without this check anyone allowed to build messages could hand out -
    and so give themselves - roles above their own through the bot."""
    for role in roles:
        problem = role_problem(role, creator, guild.me)
        if problem is not None:
            return role_problem_text(language, problem, role.id)

    return None


def role_select(language: SupportedLanguage, action: Action) -> RoleSelect:
    """The role picker of the screen, with the roles already chosen pre-selected."""
    defaults = [
        SelectDefaultValue(id=role_id, type=SelectDefaultValueType.role) for role_id in action.roles[:MAX_ROLES_PER_ACTION]
    ]

    return RoleSelect(
        placeholder=t(language, f"action_screen.role.roles_placeholder.{action.type.value}"),
        min_values=1,
        max_values=MAX_ROLES_PER_ACTION,
        default_values=defaults,
    )


def type_line(language: SupportedLanguage, action: Action) -> str:
    """The type of an action as its screen shows it: in capitals, in a code span."""
    return f"`{action_name(language, action.type, len(action.roles)).upper()}`"


def role_sections(language: SupportedLanguage, action: Action) -> list[Section]:
    """The parts of the summary of a role action: its type and its roles."""
    roles = (
        [", ".join(f"<@&{role_id}>" for role_id in action.roles)]
        if action.roles
        else [t(language, "action_screen.role.no_roles")]
    )
    return [
        Section(
            ROLE_SECTION_EMOJIS["type"],
            t(language, "action_screen.section.type"),
            [type_line(language, action)],
            inline=True,
        ),
        Section(
            ROLE_SECTION_EMOJIS["roles"],
            t(language, "action_screen.section.roles", count=len(action.roles)),
            roles,
            spaced=True,
            divided=True,
        ),
    ]


def with_payload(action: Action, payload: MessagePayload) -> Action:
    """The message action with another message."""
    return replace(action, payload=payload)


def with_channel(action: Action, channel_id: int | None) -> Action:
    """The "channel message" action with another channel."""
    return replace(action, channel_id=channel_id)


def channel_select(language: SupportedLanguage, action: Action) -> ChannelSelect:
    """The channel picker of the screen of a "channel message" action, with the chosen channel pre-selected."""
    defaults = (
        [SelectDefaultValue(id=action.channel_id, type=SelectDefaultValueType.channel)]
        if action.channel_id is not None
        else []
    )

    return ChannelSelect(
        channel_types=TARGET_CHANNEL_TYPES,
        placeholder=t(language, "action_screen.message.channel_placeholder"),
        default_values=defaults,
    )


def message_preview(
    language: SupportedLanguage, member: Member, channel: GuildChannel | Thread, questions: Sequence[str] = ()
) -> Callable[[str], str]:
    """What fills the variables of a message while it is edited: test data. The person who sets it up (`member`)
    stands in for the person who uses the button, the channel of the editor for the channel, and every question of a
    form has a sample answer."""
    guild = channel.guild
    sample = t(language, "action_screen.message.sample_answer")
    answers = [(question, f"{sample} {number}") for number, question in enumerate(questions, 1)]

    def preview(text: str) -> str:
        """`text` with its variables filled with the test data."""
        return render_variables(text, member=member, guild=guild, channel=channel, answers=answers)

    return preview


def _variable_key(name: str) -> str:
    """The key under `action_screen.variables` that explains a variable (`answer.1` explains `answer.N`)."""
    return "answer" if name.startswith("answer.") else name.replace(".", "_")


def variables_help(language: SupportedLanguage, *, in_form: bool) -> str:
    """The list of variables a message may use, for the info text of its screen. The answers of a form can only be
    used by what the form does once it is submitted."""
    names = (*VARIABLES, *FORM_VARIABLES) if in_form else VARIABLES
    lines = [f"**{t(language, 'action_screen.variables.title')}:**"]
    lines += [f"> `{{{name}}}` - {t(language, f'action_screen.variables.{_variable_key(name)}')}" for name in names]
    return "\n".join(lines)


def message_lines(
    language: SupportedLanguage, payload: MessagePayload | None, preview: Callable[[str], str] | None = None
) -> list[str]:
    """What a message action sends, as lines: its text exactly as it was written - with the variables filled by
    `preview`, if given. A message that carries a template is not shown by its text (that of the template is not
    meant to be edited here): the line says which template it uses. Too much of it is cut short."""
    if payload is None or payload.is_empty:
        return [t(language, "editor.payload.empty")]

    if payload.kind is not PayloadKind.TEXT:
        name = (payload.template_name or "?").replace("`", "'")
        return [t(language, f"editor.payload.{payload.kind.value}", name=name)]

    text = payload.text.strip()
    lines = (preview(text) if preview is not None else text).strip().splitlines() if text else []
    return fit_lines(lines, lambda hidden: t(language, "editor.section.more", amount=hidden))


def message_sections(
    language: SupportedLanguage, action: Action, *, preview: Callable[[str], str] | None = None
) -> list[Section]:
    """The parts of the summary of a message action: its type, its message and - for a channel message - its channel.
    The message is shown as it is written (not quoted), with its variables filled by `preview`."""
    sections = [
        Section(
            MESSAGE_SECTION_EMOJIS["type"],
            t(language, "action_screen.section.type"),
            [type_line(language, action)],
            inline=True,
        ),
        Section(
            MESSAGE_SECTION_EMOJIS["message"],
            t(language, "action_screen.section.message"),
            message_lines(language, action.payload, preview),
            spaced=True,
            quoted=False,
            divided=True,
        ),
    ]

    if action.type is ActionType.SEND_CHANNEL:
        channel = (
            f"<#{action.channel_id}>" if action.channel_id is not None else t(language, "action_screen.message.no_channel")
        )
        sections.append(
            Section(
                MESSAGE_SECTION_EMOJIS["channel"],
                t(language, "action_screen.section.channel"),
                [channel],
                inline=True,
                spaced=True,
            )
        )
    return sections


def screen_texts(language: SupportedLanguage, action: Action) -> tuple[str, str]:
    """The title and the description of the screen of a role action or message action."""
    group = "role" if action.type in ROLE_ACTIONS else "message"
    description = t(language, f"action_screen.{group}.description")
    if action.type is ActionType.ROLE_SET:
        description = f"{description} {t(language, 'action_screen.role.set_help')}"
    return t(language, f"action_screen.{group}.title"), description
