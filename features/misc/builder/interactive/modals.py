import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

from discord import Guild, Interaction, Member, Role, SelectOption, TextStyle
from discord import RadioGroupOption as RadioOption
from discord.ui import Label, Modal, RadioGroup, RoleSelect, Select, TextInput

from core.discord_api.limits import (
    MAX_BUTTON_LABEL,
    MAX_BUTTON_URL,
    MAX_MESSAGE_CONTENT,
    MAX_MODAL_TEXTINPUT,
    MAX_MODAL_TEXTINPUT_PLACEHOLDER,
    MAX_MODAL_TITLE,
    MAX_SELECT_ITEMS,
    MAX_SELECT_OPTION_DESCRIPTION,
    MAX_SELECT_OPTION_LABEL,
    MAX_SELECT_PLACEHOLDER,
)
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.interactive.draft import (
    BUTTON_STYLES,
    MAX_EMOJI_LENGTH,
    DraftKind,
    InteractiveLibrary,
    ItemDraft,
    OptionDraft,
)
from features.misc.builder.interactive.editor import conflict_text, problem_text
from features.misc.builder.interactive.messages import role_problem_text, t
from features.misc.builder.interactive.models import (
    CONDITION_PERMISSIONS,
    MAX_CONDITION_ROLES,
    MAX_QUESTION_LABEL,
    MAX_QUESTIONS_PER_FORM,
    Condition,
    ConditionType,
    ConfigProblem,
    ItemConfig,
    MessagePayload,
    PayloadKind,
    Question,
    SelectMode,
    condition_conflicts,
    validate_config,
    validate_question,
)
from features.misc.builder.interactive.roles import role_problem
from features.misc.builder.interactive.templates import TemplateChoice, TemplateChoices
from features.misc.builder.validation import convert_to_emoji, is_valid_url

AfterButton = Callable[[Interaction, int | None, str | None], Awaitable[None]]
"""Called when a button modal is done: the interaction, the id of the button to show next and an error text, if any."""

AfterEdit = Callable[[Interaction, str | None], Awaitable[None]]
"""Called when an action or condition modal is done: the interaction and an error text, if any."""


def _title(language: SupportedLanguage, key: str) -> str:
    """The translated modal title, cut to Discord's limit."""
    return t(language, key)[:MAX_MODAL_TITLE]


def _roles_by_id(guild: Guild | None, role_ids: tuple[int, ...]) -> list[Role]:
    """The roles that still exist, to pre-select in a role picker."""
    if guild is None:
        return []
    return [role for role_id in role_ids if (role := guild.get_role(role_id)) is not None]


def _role_select(guild: Guild | None, existing: tuple[int, ...], *, maximum: int) -> RoleSelect:
    """A role picker that needs at least one role and offers the already chosen ones pre-selected."""
    defaults = _roles_by_id(guild, existing)
    if defaults:
        return RoleSelect(min_values=1, max_values=maximum, default_values=defaults)
    return RoleSelect(min_values=1, max_values=maximum)


class ButtonModal(Modal):
    """Modal to create or restyle a button: its text, emoji and - depending on the kind - its URL or colour."""

    def __init__(
        self,
        language: SupportedLanguage,
        library: InteractiveLibrary,
        kind: DraftKind,
        draft: ItemDraft | None,
        after: AfterButton,
    ) -> None:
        """`draft` is the button to change, or `None` to create a new one of `kind`; `after` shows the next screen."""
        super().__init__(title=_title(language, f"modals.button.title.{kind.value}"))
        self.language = language
        self.library = library
        self.kind = kind
        self.draft = draft
        self.after = after

        self.label_input: TextInput = TextInput(
            label=t(language, "modals.button.label.question"),
            placeholder=t(language, "modals.button.label.placeholder"),
            required=False,
            max_length=MAX_BUTTON_LABEL,
            default=draft.label if draft else None,
        )
        self.emoji_input: TextInput = TextInput(
            label=t(language, "modals.button.emoji.question"),
            placeholder=t(language, "modals.button.emoji.placeholder"),
            required=False,
            max_length=MAX_EMOJI_LENGTH,
            default=draft.emoji if draft else None,
        )
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)

        self.url_input: TextInput | None = None
        self.style_input: RadioGroup | None = None
        if kind is DraftKind.LINK:
            url_input: TextInput = TextInput(
                label=t(language, "modals.button.url.question"),
                placeholder=t(language, "modals.button.url.placeholder"),
                max_length=MAX_BUTTON_URL,
                default=draft.url if draft else None,
            )
            self.url_input = url_input
            self.add_item(url_input)
        else:
            current = draft.style if draft else None
            style_input: RadioGroup = RadioGroup(
                options=[
                    RadioOption(
                        label=t(language, f"modals.button.style.{name}"),
                        value=name,
                        default=(style == current) if current else name == "secondary",
                    )
                    for name, style in BUTTON_STYLES.items()
                ]
            )
            self.style_input = style_input
            self.add_item(Label(text=t(language, "modals.button.style.question"), component=style_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the input, then create or update the button and hand over to the next screen."""
        guild = interaction.guild
        assert guild is not None
        language = self.language
        current_id = self.draft.id if self.draft else None

        label = self.label_input.value.strip() or None
        emoji_text = self.emoji_input.value.strip()
        emoji = convert_to_emoji(emoji_text, guild) if emoji_text else None
        url = self.url_input.value.strip() if self.url_input is not None else None

        error: str | None = None
        if emoji_text and emoji is None:
            error = t(language, "errors.invalid_emoji")
        elif label is None and emoji is None:
            error = t(language, "errors.label_or_emoji")
        elif self.kind is DraftKind.LINK and (url is None or len(url) > MAX_BUTTON_URL or not is_valid_url(url)):
            error = t(language, "errors.invalid_url")
        elif self.draft is None and self.library.is_full:
            error = t(language, "errors.library_full")

        if error is not None:
            await self.after(interaction, current_id, error)
            return

        style = BUTTON_STYLES.get(self.style_input.value or "", BUTTON_STYLES["secondary"]) if self.style_input else None
        if self.draft is None:
            fields: dict[str, object] = {"label": label, "emoji": emoji}
            if self.kind is DraftKind.LINK:
                fields["url"] = url
            elif style is not None:
                fields["style"] = style
            draft = self.library.new_draft(self.kind, **fields)
        else:
            draft = self.draft
            draft.label, draft.emoji = label, emoji
            if self.kind is DraftKind.LINK:
                draft.url = url
            elif style is not None:
                draft.style = style

        await self.after(interaction, draft.id, None)


class ConditionModal(Modal):
    """Modal to add a restriction to a button, or to change an existing one. "Once per user" needs none."""

    def __init__(
        self,
        language: SupportedLanguage,
        config: ItemConfig,
        guild: Guild | None,
        condition_type: ConditionType,
        index: int | None,
        after: AfterEdit,
        *,
        inherited: Sequence[Condition] = (),
        dependents: Sequence[ItemConfig] = (),
    ) -> None:
        """`config` holds the restrictions, `index` is the position of the restriction to change or `None` to add
        a new one of `condition_type`. `inherited` are the restrictions of the dropdown an option belongs to;
        `dependents` are the options of a dropdown, whose actions run under its restrictions."""
        super().__init__(title=_title(language, f"modals.condition.title.{condition_type.value}"))
        self.language = language
        self.config = config
        self.inherited = inherited
        self.dependents = dependents
        self.condition_type = condition_type
        self.index = index
        self.after = after

        existing = config.conditions[index] if index is not None else None
        self.roles_input: RoleSelect | None = None
        self.match_input: RadioGroup | None = None
        self.permissions_input: Select | None = None
        self.amount_input: TextInput | None = None

        if condition_type in (ConditionType.ROLE_REQUIRED, ConditionType.ROLE_FORBIDDEN):
            roles_input = _role_select(guild, existing.roles if existing else (), maximum=MAX_CONDITION_ROLES)
            self.roles_input = roles_input
            self.add_item(Label(text=t(language, f"modals.condition.roles.{condition_type.value}"), component=roles_input))

        if condition_type is ConditionType.ROLE_REQUIRED:
            match_all = existing.match_all if existing else False
            match_input: RadioGroup = RadioGroup(
                options=[
                    RadioOption(label=t(language, "modals.condition.match.any"), value="any", default=not match_all),
                    RadioOption(label=t(language, "modals.condition.match.all"), value="all", default=match_all),
                ]
            )
            self.match_input = match_input
            self.add_item(Label(text=t(language, "modals.condition.match.question"), component=match_input))

        if condition_type is ConditionType.PERMISSIONS:
            chosen = existing.permissions if existing else ()
            permissions_input: Select = Select(
                min_values=1,
                max_values=len(CONDITION_PERMISSIONS),
                options=[
                    SelectOption(
                        label=translate(language, f"errors.permissions.{name}")[:100], value=name, default=name in chosen
                    )
                    for name in CONDITION_PERMISSIONS
                ],
            )
            self.permissions_input = permissions_input
            self.add_item(
                Label(
                    text=t(language, "modals.condition.permissions.question"),
                    description=t(language, "modals.condition.permissions.help"),
                    component=permissions_input,
                )
            )

        if condition_type in (ConditionType.ACCOUNT_AGE, ConditionType.MEMBER_AGE, ConditionType.COOLDOWN):
            amount_input: TextInput = TextInput(
                label=t(language, f"modals.condition.amount.{condition_type.value}"),
                placeholder=t(language, f"modals.condition.amount.{condition_type.value}_placeholder"),
                min_length=1,
                max_length=5,
                default=str(existing.amount) if existing and existing.amount else None,
            )
            self.amount_input = amount_input
            self.add_item(amount_input)

    def _build(self) -> Condition | None:
        """The condition the inputs describe, or `None` if the amount is not a whole number."""
        if self.roles_input is not None:
            roles = tuple(role.id for role in self.roles_input.values)
            match_all = self.match_input is not None and self.match_input.value == "all"
            return Condition(self.condition_type, roles=roles, match_all=match_all)

        if self.permissions_input is not None:
            return Condition(self.condition_type, permissions=tuple(self.permissions_input.values))

        if self.amount_input is not None:
            text = self.amount_input.value.strip()
            # Discord offers no field that takes only digits, so anything else is refused when it is sent.
            return Condition(self.condition_type, amount=int(text)) if text.isascii() and text.isdecimal() else None

        return Condition(self.condition_type)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the restriction as a whole, then store it."""
        condition = self._build()
        conditions = list(self.config.conditions)

        if condition is None:
            await self.after(interaction, problem_text(self.language, ConfigProblem.CONDITION_INVALID_AMOUNT))
            return

        if self.index is None:
            conditions.append(condition)
        else:
            conditions[self.index] = condition

        problems = validate_config(replace(self.config, conditions=conditions), inherited=self.inherited)
        if problems:
            text = conflict_text(
                self.language, problems[0], actions=self.config.actions, conditions=[*conditions, *self.inherited]
            )
            await self.after(interaction, text)
            return

        for dependent in self.dependents:  # the options of a dropdown run under its restrictions as well
            covering = [*dependent.conditions, *conditions]
            found = condition_conflicts(dependent.actions, covering)
            if found:
                await self.after(
                    interaction, conflict_text(self.language, found[0], actions=dependent.actions, conditions=covering)
                )
                return

        self.config.conditions[:] = conditions
        await self.after(interaction, None)


AfterOption = Callable[[Interaction, str | None, str | None], Awaitable[None]]
"""Called when an option modal is done: the interaction, the key of the option to show next and an error text, if any."""


def _template_select(choices: list[TemplateChoice], selected: str | None) -> Select:
    """A dropdown of saved templates in which none (or one) can be chosen."""
    return Select(
        required=False,
        min_values=0,
        max_values=1,
        options=[
            SelectOption(label=choice.name[:100], value=choice.name, emoji=choice.icon, default=choice.name == selected)
            for choice in choices
        ],
    )


AfterContent = Callable[[Interaction, MessagePayload | None, str | None], Awaitable[None]]
"""Called when the modal of a message is done: the interaction, the message it describes and an error text, if any."""


class MessageContentModal(Modal):
    """Modal to write the message of a message action: a text, or a saved embed or container template."""

    def __init__(
        self,
        language: SupportedLanguage,
        payload: MessagePayload | None,
        templates: TemplateChoices,
        after: AfterContent,
    ) -> None:
        """`payload` is the message so far, `templates` the saved templates a snapshot can be taken of."""
        super().__init__(title=_title(language, "modals.message_action.title"))
        self.language = language
        self.after = after
        self.templates = templates

        # The question is the text of the `Label` around the input - Discord refuses a label on the input itself.
        self.text_input: TextInput = TextInput(
            placeholder=t(language, "modals.message_action.text.placeholder"),
            style=TextStyle.paragraph,
            required=False,
            max_length=MAX_MESSAGE_CONTENT,
            # A template brings its own text, which is not the one to edit here.
            default=payload.text if payload is not None and payload.kind is PayloadKind.TEXT and payload.text else None,
        )
        self.add_item(Label(text=t(language, "modals.message_action.text.question"), component=self.text_input))

        self.embed_input: Select | None = None
        self.container_input: Select | None = None
        if templates.embed:
            chosen = payload.template_name if payload is not None and payload.kind is PayloadKind.EMBED else None
            embed_input = _template_select(templates.embed, chosen)
            self.embed_input = embed_input
            self.add_item(
                Label(
                    text=t(language, "modals.message_action.template.question"),
                    description=t(language, "modals.message_action.embed.help"),
                    component=embed_input,
                )
            )
        if templates.container:
            chosen = payload.template_name if payload is not None and payload.kind is PayloadKind.CONTAINER else None
            container_input = _template_select(templates.container, chosen)
            self.container_input = container_input
            self.add_item(
                Label(
                    text=t(language, "modals.message_action.template.question"),
                    description=t(language, "modals.message_action.container.help"),
                    component=container_input,
                )
            )

    def _payload(self) -> tuple[MessagePayload | None, str | None]:
        """The payload the inputs describe, or an error text if they do not describe a usable one."""
        language = self.language
        text = self.text_input.value.strip()
        embed_name = self.embed_input.values[0] if self.embed_input and self.embed_input.values else None
        container_name = self.container_input.values[0] if self.container_input and self.container_input.values else None

        if embed_name and container_name:
            return None, t(language, "errors.payload_one_template")

        if embed_name:
            choice = next((entry for entry in self.templates.embed if entry.name == embed_name), None)
            if choice is None:
                return None, t(language, "errors.template_gone")

            # The template replaces the text, as the container template does: the text of the input is not meant for it
            # (and it often is only the example the screen started with) - what the template says is sent.
            return MessagePayload(choice.content, PayloadKind.EMBED, choice.name, choice.data), None

        if container_name:
            choice = next((entry for entry in self.templates.container if entry.name == container_name), None)
            if choice is None:
                return None, t(language, "errors.template_gone")
            return MessagePayload("", PayloadKind.CONTAINER, choice.name, choice.data), None

        return MessagePayload(text), None

    async def on_submit(self, interaction: Interaction) -> None:
        """Hand the message over - or the reason it cannot be used."""
        payload, error = self._payload()
        if error is None and (payload is None or payload.is_empty):
            error = problem_text(self.language, ConfigProblem.PAYLOAD_EMPTY)
        await self.after(interaction, None if error is not None else payload, error)


class SelectLookModal(Modal):
    """Modal for a dropdown's placeholder and how many options may be chosen: to change those of a dropdown, or to
    create a new one."""

    def __init__(
        self,
        language: SupportedLanguage,
        draft: ItemDraft | None,
        after: AfterButton,
        *,
        library: InteractiveLibrary | None = None,
        mode: SelectMode = SelectMode.STRINGS,
    ) -> None:
        """`draft` is the dropdown to change. With `None`, a new dropdown of `mode` is created in `library` once the
        input is valid (so closing the modal creates nothing). `after` shows the next screen: it gets the id of the
        dropdown - `None` if there is none - and an error text, if any."""
        super().__init__(title=_title(language, "modals.select.title"))
        assert draft is not None or library is not None, "a new dropdown needs the library to be created in"
        self.language = language
        self.draft = draft
        self.library = library
        self.mode = mode
        self.after = after

        self.placeholder_input: TextInput = TextInput(
            label=t(language, "modals.select.placeholder.question"),
            placeholder=t(language, "modals.select.placeholder.placeholder"),
            required=False,
            max_length=MAX_SELECT_PLACEHOLDER,
            default=draft.placeholder if draft else None,
        )
        self.min_input: TextInput = TextInput(
            label=t(language, "modals.select.min.question"),
            placeholder=t(language, "modals.select.min.placeholder"),
            max_length=2,
            default=str(draft.min_values) if draft else "1",
        )
        self.max_input: TextInput = TextInput(
            label=t(language, "modals.select.max.question"),
            placeholder=t(language, "modals.select.max.placeholder"),
            max_length=2,
            default=str(draft.max_values) if draft else "1",
        )
        self.add_item(self.placeholder_input)
        self.add_item(self.min_input)
        self.add_item(self.max_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the limits (0 to 25 choices, at least one at most), then store the changes or create the dropdown."""
        current_id = self.draft.id if self.draft else None
        minimum, maximum = self.min_input.value.strip(), self.max_input.value.strip()
        valid = (
            minimum.isdecimal()
            and maximum.isdecimal()
            and 0 <= int(minimum) <= int(maximum) <= MAX_SELECT_ITEMS
            and int(maximum) >= 1
        )
        if not valid:
            await self.after(interaction, current_id, problem_text(self.language, ConfigProblem.INVALID_SELECTION_RANGE))
            return

        placeholder = self.placeholder_input.value.strip() or None
        if self.draft is None:
            assert self.library is not None
            if self.library.is_full:
                await self.after(interaction, None, t(self.language, "errors.library_full"))
                return
            draft = self.library.new_draft(
                DraftKind.SELECT,
                mode=self.mode,
                placeholder=placeholder,
                min_values=int(minimum),
                max_values=int(maximum),
            )
        else:
            draft = self.draft
            draft.placeholder = placeholder
            draft.min_values, draft.max_values = int(minimum), int(maximum)
        await self.after(interaction, draft.id, None)


class OptionModal(Modal):
    """Modal to add an option to a dropdown of texts, or to change how an existing option looks."""

    def __init__(
        self, language: SupportedLanguage, draft: ItemDraft, option: OptionDraft | None, after: AfterOption
    ) -> None:
        """`option` is the option to change, or `None` to add a new one; `after` shows the next screen."""
        super().__init__(title=_title(language, "modals.option.title"))
        self.language = language
        self.draft = draft
        self.option = option
        self.after = after

        self.label_input: TextInput = TextInput(
            label=t(language, "modals.option.label.question"),
            placeholder=t(language, "modals.option.label.placeholder"),
            max_length=MAX_SELECT_OPTION_LABEL,
            default=option.label if option else None,
        )
        self.emoji_input: TextInput = TextInput(
            label=t(language, "modals.option.emoji.question"),
            placeholder=t(language, "modals.button.emoji.placeholder"),
            required=False,
            max_length=MAX_EMOJI_LENGTH,
            default=option.emoji if option else None,
        )
        self.description_input: TextInput = TextInput(
            label=t(language, "modals.option.description.question"),
            placeholder=t(language, "modals.option.description.placeholder"),
            required=False,
            max_length=MAX_SELECT_OPTION_DESCRIPTION,
            default=option.description if option else None,
        )
        self.add_item(self.label_input)
        self.add_item(self.emoji_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the input, then add or update the option."""
        guild = interaction.guild
        assert guild is not None
        language = self.language
        current_key = self.option.key if self.option else None

        label = self.label_input.value.strip()
        emoji_text = self.emoji_input.value.strip()
        emoji = convert_to_emoji(emoji_text, guild) if emoji_text else None
        description = self.description_input.value.strip() or None

        error: str | None = None
        if emoji_text and emoji is None:
            error = t(language, "errors.invalid_emoji")
        elif not label:
            error = t(language, "errors.option_label")
        elif self.option is None and len(self.draft.options) >= MAX_SELECT_ITEMS:
            error = problem_text(language, ConfigProblem.TOO_MANY_OPTIONS)

        if error is not None:
            await self.after(interaction, current_key, error)
            return

        if self.option is None:
            created = self.draft.add_option(label, emoji=emoji, description=description)
            await self.after(interaction, created.key, None)
            return

        self.option.label, self.option.emoji, self.option.description = label, emoji, description
        await self.after(interaction, self.option.key, None)


class RoleOptionsModal(Modal):
    """Modal to add roles to a role dropdown: every chosen role becomes an option named after it."""

    def __init__(self, language: SupportedLanguage, draft: ItemDraft, after: AfterOption) -> None:
        """`after` shows the next screen once the options are added."""
        super().__init__(title=_title(language, "modals.role_options.title"))
        self.language = language
        self.draft = draft
        self.after = after

        room = max(MAX_SELECT_ITEMS - len(draft.options), 1)
        self.roles_input: RoleSelect = RoleSelect(min_values=1, max_values=room)
        self.add_item(
            Label(
                text=t(language, "modals.role_options.question"),
                description=t(language, "modals.role_options.help", max=room),
                component=self.roles_input,
            )
        )

    async def on_submit(self, interaction: Interaction) -> None:
        """Check that every chosen role may be handed out by this user, then add the ones not offered yet."""
        guild = interaction.guild
        member = interaction.user
        assert guild is not None and isinstance(member, Member)

        roles = [role for role in self.roles_input.values if isinstance(role, Role)]
        for role in roles:
            problem = role_problem(role, member, guild.me)
            if problem is not None:
                await self.after(interaction, None, role_problem_text(self.language, problem, role.id))
                return

        offered = {option.role_id for option in self.draft.options}
        fresh = [role for role in roles if role.id not in offered]
        if len(self.draft.options) + len(fresh) > MAX_SELECT_ITEMS:
            await self.after(interaction, None, problem_text(self.language, ConfigProblem.TOO_MANY_OPTIONS))
            return

        last: str | None = None
        for role in fresh:
            last = self.draft.add_option(role.name[:MAX_SELECT_OPTION_LABEL], role_id=role.id).key
        await self.after(interaction, last, None)


AfterQuestion = Callable[[Interaction, int | None, str | None], Awaitable[None]]
"""Called when a question modal is done: the interaction, the position of the question to show next and an error text."""

_LENGTH: re.Pattern[str] = re.compile(r"\s*(?:(\d+)\s*-\s*)?(\d+)\s*")


def parse_length(text: str) -> tuple[int, int] | None:
    """The shortest and longest answer a text like "10-500" (or just "500") allows; an empty text allows any length.
    `None` if the text is not a valid range."""
    if not text.strip():
        return 0, MAX_MODAL_TEXTINPUT

    match = _LENGTH.fullmatch(text)
    if match is None:
        return None

    minimum, maximum = int(match.group(1) or 0), int(match.group(2))
    return (minimum, maximum) if 1 <= maximum <= MAX_MODAL_TEXTINPUT and minimum <= maximum else None


def _length_text(question: Question | None) -> str | None:
    """A question's length limits as the user types them - nothing if it has none."""
    if question is None or (question.min_length == 0 and question.max_length == MAX_MODAL_TEXTINPUT):
        return None
    return f"{question.min_length}-{question.max_length}" if question.min_length else str(question.max_length)


class FormLookModal(Modal):
    """Modal to create a form or to rename one: the title shown above its questions."""

    def __init__(
        self, language: SupportedLanguage, library: InteractiveLibrary, draft: ItemDraft | None, after: AfterButton
    ) -> None:
        """`draft` is the form to rename, or `None` to create a new one; `after` shows the next screen."""
        super().__init__(title=_title(language, "modals.form.title"))
        self.language = language
        self.library = library
        self.draft = draft
        self.after = after

        self.title_input: TextInput = TextInput(
            label=t(language, "modals.form.name.question"),
            placeholder=t(language, "modals.form.name.placeholder"),
            max_length=MAX_MODAL_TITLE,
            default=draft.label if draft else None,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Store the title, creating the form if it is a new one."""
        title = self.title_input.value.strip()
        if not title:
            await self.after(interaction, self.draft.id if self.draft else None, t(self.language, "errors.form_title"))
            return

        if self.draft is None:
            if self.library.is_full:
                await self.after(interaction, None, t(self.language, "errors.library_full"))
                return
            self.draft = self.library.new_draft(DraftKind.FORM, label=title)
        else:
            self.draft.label = title
        await self.after(interaction, self.draft.id, None)


class QuestionModal(Modal):
    """Modal to add a question to a form or to change one: its text, hint, format and length."""

    def __init__(self, language: SupportedLanguage, draft: ItemDraft, index: int | None, after: AfterQuestion) -> None:
        """`index` is the position of the question to change, or `None` to add a new one."""
        super().__init__(title=_title(language, "modals.question.title"))
        self.language = language
        self.draft = draft
        self.index = index
        self.after = after

        existing = draft.questions[index] if index is not None else None
        self.label_input: TextInput = TextInput(
            label=t(language, "modals.question.label.question"),
            placeholder=t(language, "modals.question.label.placeholder"),
            max_length=MAX_QUESTION_LABEL,
            default=existing.label if existing else None,
        )
        self.hint_input: TextInput = TextInput(
            label=t(language, "modals.question.hint.question"),
            placeholder=t(language, "modals.question.hint.placeholder"),
            required=False,
            max_length=MAX_MODAL_TEXTINPUT_PLACEHOLDER,
            default=existing.placeholder if existing else None,
        )
        paragraph = existing.paragraph if existing else False
        self.format_input: RadioGroup = RadioGroup(
            options=[
                RadioOption(label=t(language, "modals.question.format.short"), value="short", default=not paragraph),
                RadioOption(label=t(language, "modals.question.format.paragraph"), value="paragraph", default=paragraph),
            ]
        )
        required = existing.required if existing else True
        self.required_input: RadioGroup = RadioGroup(
            options=[
                RadioOption(label=t(language, "modals.question.required.yes"), value="yes", default=required),
                RadioOption(label=t(language, "modals.question.required.no"), value="no", default=not required),
            ]
        )
        self.length_input: TextInput = TextInput(
            label=t(language, "modals.question.length.question"),
            placeholder=t(language, "modals.question.length.placeholder"),
            required=False,
            max_length=10,
            default=_length_text(existing),
        )
        self.add_item(self.label_input)
        self.add_item(self.hint_input)
        self.add_item(self.length_input)  # what may be typed in the field: its hint and its length belong together
        self.add_item(Label(text=t(language, "modals.question.format.question"), component=self.format_input))
        self.add_item(Label(text=t(language, "modals.question.required.question"), component=self.required_input))

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the question, then add it or replace the one at `index`."""
        language = self.language
        questions = self.draft.questions
        limits = parse_length(self.length_input.value)

        error: str | None = None
        if self.index is None and len(questions) >= MAX_QUESTIONS_PER_FORM:
            error = problem_text(language, ConfigProblem.TOO_MANY_QUESTIONS)
        elif not self.label_input.value.strip() or limits is None:
            error = problem_text(language, ConfigProblem.INVALID_QUESTION)

        if error is not None or limits is None:
            await self.after(interaction, self.index, error)
            return

        question = Question(
            label=self.label_input.value.strip(),
            placeholder=self.hint_input.value.strip() or None,
            paragraph=self.format_input.value == "paragraph",
            required=self.required_input.value != "no",
            min_length=limits[0],
            max_length=limits[1],
        )
        if not validate_question(question):
            await self.after(interaction, self.index, problem_text(language, ConfigProblem.INVALID_QUESTION))
            return

        if self.index is None:
            questions.append(question)
            await self.after(interaction, len(questions) - 1, None)
            return

        questions[self.index] = question
        await self.after(interaction, self.index, None)
