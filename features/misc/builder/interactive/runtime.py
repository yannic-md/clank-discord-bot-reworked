import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from logging import Logger
from re import Match
from typing import Any, Self

from discord import (
    AllowedMentions,
    ButtonStyle,
    Forbidden,
    Interaction,
    Member,
    PartialEmoji,
    SelectOption,
    TextStyle,
)
from discord.ui import Button, DynamicItem, Item, Label, Modal, Select, TextInput

from core.db.repositories.interactive_builder.interactive_item_repository import (
    get_item,
    has_used,
    release_use,
    reserve_use,
)
from core.enums.language import SupportedLanguage
from core.i18n.resolve import get_language
from core.setup.errors import error_handler
from features.misc.builder.interactive.conditions import ConditionFailure, CooldownTracker, check_conditions
from features.misc.builder.interactive.executor import (
    ClickContext,
    ExecutionResult,
    execute_actions,
    execute_role_menu,
)
from features.misc.builder.interactive.messages import condition_failure_text, t
from features.misc.builder.interactive.models import (
    Action,
    ActionType,
    Condition,
    ConditionType,
    FormConfig,
    ItemConfig,
    ItemKind,
    SelectConfig,
    SelectMode,
    is_restricted,
)

logger: Logger = logging.getLogger("discord")

BUTTON_PREFIX: str = "ibtn"
"""`custom_id` prefix of interactive buttons: `ibtn:<item id>`."""
SELECT_PREFIX: str = "isel"
"""`custom_id` prefix of interactive dropdowns: `isel:<item id>`."""
FORM_PREFIX: str = "iform"
"""`custom_id` prefix of the form (modal) of a form item: `iform:<item id>`."""

cooldowns: CooldownTracker = CooldownTracker()


@dataclass
class Outcome:
    """What running one button or dropdown option led to: the text for the user (possibly empty) and whether it replied."""

    text: str = ""
    replied: bool = False


def _find_condition(conditions: Sequence[Condition], condition_type: ConditionType) -> Condition | None:
    """The restriction of this type among the conditions, or `None`."""
    return next((condition for condition in conditions if condition.type is condition_type), None)


def _check_cooldown(conditions: Sequence[Condition], key: tuple[int, str, int]) -> ConditionFailure | None:
    """Fail with the time left if the user is still on cooldown for this item."""
    cooldown = _find_condition(conditions, ConditionType.COOLDOWN)
    if cooldown is None:
        return None

    remaining = cooldowns.remaining(key)
    return ConditionFailure(cooldown, remaining) if remaining > 0 else None


async def _run(
    click: ClickContext,
    item_id: int,
    option_key: str,
    conditions: Sequence[Condition],
    execute: Callable[[], Awaitable[ExecutionResult]],
) -> Outcome:
    """Check who may use the item (option), then carry it out and report the outcome.

    `execute` runs the actual actions. A failing check explains itself and runs nothing; a use that is counted
    ("once per person") is given back if the actions fail, as nothing happened for the user then.
    """
    member, language = click.member, click.language
    cooldown_key = (item_id, option_key, member.id)

    failure = check_conditions(member, conditions) or _check_cooldown(conditions, cooldown_key)
    if failure is not None:
        return Outcome(text=condition_failure_text(language, failure))

    # Reserved before the actions run, so two quick clicks cannot both get past "once per person".
    reserved = False
    once = _find_condition(conditions, ConditionType.ONCE_PER_USER)
    if once is not None:
        reserved = await reserve_use(item_id, option_key, member.id)
        if not reserved:
            return Outcome(text=condition_failure_text(language, ConditionFailure(once)))

    try:
        result = await execute()
    except Forbidden:
        if reserved:
            await release_use(item_id, option_key, member.id)
        return Outcome(text=t(language, "errors.role_forbidden"))
    except Exception:
        if reserved:
            await release_use(item_id, option_key, member.id)
        raise

    cooldown = _find_condition(conditions, ConditionType.COOLDOWN)
    if cooldown is not None:
        cooldowns.start(cooldown_key, cooldown.amount)
    return Outcome(text=result.text, replied=result.replied)


async def _begin(interaction: Interaction) -> tuple[ClickContext, SupportedLanguage] | None:
    """Who is using the item and in which language to answer - `None` outside of a server."""
    member = interaction.user
    if interaction.guild is None or not isinstance(member, Member):
        return None

    language = await get_language(interaction)
    return ClickContext(interaction, member, language), language


async def _finish(click: ClickContext, outcomes: Sequence[Outcome]) -> None:
    """Answer the (deferred) click with the collected texts - each outcome already says what happened. Only a
    dropdown that may be left empty gets here with nothing to say, and then tells why nothing ran."""
    texts = [outcome.text for outcome in outcomes if outcome.text]
    if not texts and not any(outcome.replied for outcome in outcomes):
        texts = [t(click.language, "result.no_actions" if outcomes else "result.nothing_selected")]
    if texts:
        await click.interaction.followup.send("\n".join(texts), ephemeral=True, allowed_mentions=AllowedMentions.none())


def _form_action(actions: Sequence[Action]) -> Action | None:
    """The action that opens a form, if there is one."""
    return next((action for action in actions if action.type is ActionType.OPEN_FORM), None)


async def _deny(click: ClickContext, text: str) -> None:
    """Answer a click that opens no form with `text`, visible to the user only."""
    await click.interaction.response.send_message(text, ephemeral=True, allowed_mentions=AllowedMentions.none())


async def _open_form(
    click: ClickContext, item_id: int, option_key: str, conditions: Sequence[Condition], action: Action
) -> None:
    """Open the form the item points to - if the user may use the item and the form.

    A form is the answer to the click itself, so nothing may be deferred before it. The item's own restrictions
    and the form's are checked now; "once per person" of the form is only counted once it is submitted, and
    merely looked up here, so closing the form does not use it up.
    """
    member, language = click.member, click.language
    item_key = (item_id, option_key, member.id)

    failure = check_conditions(member, conditions) or _check_cooldown(conditions, item_key)
    if failure is not None:
        await _deny(click, condition_failure_text(language, failure))
        return

    record = await get_item(action.form_id) if action.form_id is not None else None
    if record is None or record.guild_id != member.guild.id or record.kind != ItemKind.FORM.value:
        await _deny(click, t(language, "errors.form_gone"))
        return

    form = FormConfig.from_data(record.config_data)
    if not form.questions:
        await _deny(click, t(language, "errors.form_gone"))
        return

    form_key = (record.id, "", member.id)
    failure = check_conditions(member, form.conditions) or _check_cooldown(form.conditions, form_key)
    once = _find_condition(form.conditions, ConditionType.ONCE_PER_USER)
    if failure is None and once is not None and await has_used(record.id, "", member.id):
        failure = ConditionFailure(once)
    if failure is not None:
        await _deny(click, condition_failure_text(language, failure))
        return

    cooldown = _find_condition(conditions, ConditionType.COOLDOWN)
    if cooldown is not None:
        cooldowns.start(item_key, cooldown.amount)
    await click.interaction.response.send_modal(FormModal(record.id, form))


def _submitted_values(components: object) -> dict[str, str]:
    """The text each field of a submitted modal holds, by the field's `custom_id`. Reads the classic layout (fields
    in rows) as well as the newer one (fields wrapped in labels)."""
    values: dict[str, str] = {}
    if isinstance(components, list):
        for entry in components:
            values.update(_submitted_values(entry))
    elif isinstance(components, dict):
        custom_id, value = components.get("custom_id"), components.get("value")
        if isinstance(custom_id, str) and isinstance(value, str):
            values[custom_id] = value
        for key in ("components", "component"):
            values.update(_submitted_values(components.get(key)))
    return values


async def handle_form_submit(interaction: Interaction) -> None:
    """Carry out a submitted form: check again who may use it, then run what the form does with the answers.

    Runs for every submission of a form modal, whether or not the modal object that was shown still exists - so
    it works across restarts as well.
    """
    begun = await _begin(interaction)
    data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
    custom_id = data.get("custom_id", "")
    if begun is None or not isinstance(custom_id, str) or not custom_id.startswith(f"{FORM_PREFIX}:"):
        return
    click, language = begun

    form_id = int(custom_id.removeprefix(f"{FORM_PREFIX}:"))
    record = await get_item(form_id)
    if record is None or record.guild_id != click.member.guild.id or record.kind != ItemKind.FORM.value:
        await interaction.response.send_message(t(language, "errors.form_gone"), ephemeral=True)
        return

    form = FormConfig.from_data(record.config_data)
    submitted = _submitted_values(data.get("components"))
    click.answers = [
        (question.label, submitted.get(f"q{number}", "").strip()) for number, question in enumerate(form.questions)
    ]
    await interaction.response.defer(ephemeral=True)

    reason = f"Interactive builder form {form_id}"
    restricted = is_restricted(form.conditions)
    outcome = await _run(
        click,
        form_id,
        "",
        form.conditions,
        lambda: execute_actions(click, form.actions, reason=reason, restricted=restricted),
    )
    await _finish(click, [outcome])


async def handle_click(interaction: Interaction, item_id: int, option_key: str = "") -> None:
    """Run the button `item_id` for the user who clicked it: check who may, then carry out its actions.

    Everything is answered ephemerally, so only the user themselves sees the outcome.
    """
    begun = await _begin(interaction)
    if begun is None:
        return
    click, language = begun

    record = await get_item(item_id)
    if record is None or record.guild_id != click.member.guild.id or record.kind != ItemKind.BUTTON.value:
        await interaction.response.send_message(t(language, "errors.item_gone"), ephemeral=True)
        return

    config = ItemConfig.from_data(record.config_data)
    opens_form = _form_action(config.actions)
    if opens_form is not None:
        await _open_form(click, item_id, option_key, config.conditions, opens_form)
        return

    await interaction.response.defer(ephemeral=True)

    reason = f"Interactive builder item {item_id}"
    restricted = is_restricted(config.conditions)
    outcome = await _run(
        click,
        item_id,
        option_key,
        config.conditions,
        lambda: execute_actions(click, config.actions, reason=reason, restricted=restricted),
    )
    await _finish(click, [outcome])


async def handle_select(interaction: Interaction, item_id: int, values: Sequence[str]) -> None:
    """Run the dropdown `item_id` for the user who used it: every selected option on its own (in a dropdown of
    texts), or the sync of the selected roles (in a role dropdown)."""
    begun = await _begin(interaction)
    if begun is None:
        return
    click, language = begun

    record = await get_item(item_id)
    if record is None or record.guild_id != click.member.guild.id or record.kind != ItemKind.SELECT.value:
        await interaction.response.send_message(t(language, "errors.item_gone"), ephemeral=True)
        return

    select = SelectConfig.from_data(record.config_data)
    chosen = list(dict.fromkeys(values))

    # An option that opens a form answers the choice itself, so it is the only one carried out.
    if select.mode is SelectMode.STRINGS:
        for key in chosen:
            option = select.option(key)
            opens_form = _form_action(option.config.actions) if option is not None else None
            if option is not None and opens_form is not None:
                conditions = [*select.conditions, *option.config.conditions]
                await _open_form(click, item_id, key, conditions, opens_form)
                return

    await interaction.response.defer(ephemeral=True)

    reason = f"Interactive builder item {item_id}"
    outcomes: list[Outcome] = []

    if select.mode is SelectMode.ROLES:
        menu = [option.role_id for option in select.options if option.role_id is not None]
        selected = [option.role_id for option in select.options if option.role_id is not None and option.key in chosen]
        outcomes.append(
            await _run(
                click, item_id, "", select.conditions, lambda: execute_role_menu(click, menu, selected, reason=reason)
            )
        )
    else:
        for key in chosen:
            option = select.option(key)
            if option is None:
                outcomes.append(Outcome(text=t(language, "errors.option_gone")))
                continue

            conditions = [*select.conditions, *option.config.conditions]
            restricted = is_restricted(conditions)
            outcomes.append(
                await _run(
                    click,
                    item_id,
                    key,
                    conditions,
                    lambda option=option, restricted=restricted: execute_actions(  # type: ignore[misc]
                        click, option.config.actions, reason=reason, restricted=restricted
                    ),
                )
            )

    await _finish(click, outcomes)


class FormModal(Modal):
    """The modal of a form: one text field per question. It only shows the form - submissions are handled by
    `handle_form_submit`, which does not depend on this object still existing."""

    def __init__(self, form_id: int, form: FormConfig) -> None:
        """Build the fields from the form's questions; their `custom_id` is their position, `q0`, `q1`, ..."""
        super().__init__(title=form.title or "—", custom_id=f"{FORM_PREFIX}:{form_id}")
        for number, question in enumerate(form.questions):
            field: TextInput[Any] = TextInput(
                placeholder=question.placeholder,
                style=TextStyle.paragraph if question.paragraph else TextStyle.short,
                required=question.required,
                min_length=question.min_length or None,
                max_length=question.max_length,
                custom_id=f"q{number}",
            )
            self.add_item(Label(text=question.label, component=field))


class InteractiveButton(DynamicItem[Button], template=rf"{BUTTON_PREFIX}:(?P<item_id>[0-9]+)"):
    """A button whose behaviour is looked up in the database by the id in its `custom_id`.

    discord.py builds a fresh instance from the clicked message on every click, so this works
    for any message the bot ever sent - no view has to be kept in memory, and it survives restarts.
    """

    def __init__(
        self,
        item_id: int,
        *,
        label: str | None = None,
        emoji: str | PartialEmoji | None = None,
        style: ButtonStyle = ButtonStyle.secondary,
        disabled: bool = False,
    ) -> None:
        """Create the button for item `item_id` with the given look."""
        super().__init__(
            Button(label=label, emoji=emoji, style=style, disabled=disabled, custom_id=f"{BUTTON_PREFIX}:{item_id}")
        )
        self.item_id: int = item_id

    @classmethod
    async def from_custom_id(cls, interaction: Interaction, item: Item, match: Match[str], /) -> Self:
        """Rebuild the button from the clicked component, taking over how it looked."""
        assert isinstance(item, Button)
        return cls(int(match["item_id"]), label=item.label, emoji=item.emoji, style=item.style, disabled=item.disabled)

    async def callback(self, interaction: Interaction) -> None:
        """Run the item; unexpected errors go to the central handler, as discord.py would otherwise only log them."""
        try:
            await handle_click(interaction, self.item_id)
        except Exception as error:
            await error_handler(interaction, error)  # type: ignore[arg-type]


class InteractiveSelect(DynamicItem[Select], template=rf"{SELECT_PREFIX}:(?P<item_id>[0-9]+)"):
    """A dropdown whose behaviour is looked up in the database by the id in its `custom_id` - see `InteractiveButton`."""

    def __init__(
        self,
        item_id: int,
        *,
        options: list[SelectOption],
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
    ) -> None:
        """Create the dropdown for item `item_id` with the given options and limits."""
        super().__init__(
            Select(
                options=options,
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
                disabled=disabled,
                custom_id=f"{SELECT_PREFIX}:{item_id}",
            )
        )
        self.item_id: int = item_id

    @classmethod
    async def from_custom_id(cls, interaction: Interaction, item: Item, match: Match[str], /) -> Self:
        """Rebuild the dropdown from the used component, taking over how it looked."""
        assert isinstance(item, Select)
        return cls(
            int(match["item_id"]),
            options=item.options,
            placeholder=item.placeholder,
            min_values=item.min_values,
            max_values=item.max_values,
            disabled=item.disabled,
        )

    async def callback(self, interaction: Interaction) -> None:
        """Run the item for the chosen options; unexpected errors go to the central handler."""
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        raw = data.get("values", [])
        values = [value for value in raw if isinstance(value, str)] if isinstance(raw, list) else []
        try:
            await handle_select(interaction, self.item_id, values)
        except Exception as error:
            await error_handler(interaction, error)  # type: ignore[arg-type]
