from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

from discord import Interaction

from core.enums.language import SupportedLanguage
from features.misc.builder.interactive.draft import InteractiveLibrary, ItemDraft, OptionDraft
from features.misc.builder.interactive.editor import draft_name, problem_text
from features.misc.builder.interactive.messages import t
from features.misc.builder.interactive.modals import (
    AfterEdit,
    ConditionModal,
    FormLookModal,
)
from features.misc.builder.interactive.models import (
    MAX_ACTIONS_PER_ITEM,
    MAX_CONDITIONS_PER_ITEM,
    MESSAGE_ACTIONS,
    ROLE_ACTIONS,
    Action,
    ActionType,
    Condition,
    ConditionType,
    ConfigProblem,
    FormConfig,
    ItemConfig,
    SelectMode,
    action_conflicts,
    condition_conflicts,
    is_restricted,
    validate_config,
    validate_form_config,
)

AfterForm = Callable[[Interaction, ItemDraft], Awaitable[None]]
"""Shows the screen of a form once it is created - or when the user wants to change it."""

DEFAULT_MOD_PERMISSIONS: tuple[str, ...] = ("manage_messages",)
"""What "may delete the message" is limited to when the user did not pick a restriction themselves."""


def scope_of(draft: ItemDraft, option_key: str | None) -> tuple[ItemConfig, list[Condition]] | None:
    """The config whose actions and restrictions are being edited, with the restrictions it inherits.

    That is the button's own config - or, for an option of a dropdown, the option's, which inherits the
    dropdown's restrictions. `None` if the option does not exist (any more).
    """
    if option_key is None:
        return draft.config, []

    option = draft.option(option_key)
    if option is None:
        return None
    return option.config, draft.config.conditions


def dependent_configs(draft: ItemDraft, option_key: str | None) -> list[ItemConfig]:
    """The configs whose actions also run under the conditions being edited: those of the options of a dropdown when
    its own conditions are edited - an option's conditions only apply to the option."""
    if option_key is not None or not draft.is_select:
        return []
    return [option.config for option in draft.options]


async def open_action_editor(
    interaction: Interaction,
    language: SupportedLanguage,
    config: ItemConfig,
    inherited: Sequence[Condition],
    action_type: ActionType,
    index: int | None,
    after: AfterEdit,
    *,
    library: InteractiveLibrary | None = None,
    open_form: AfterForm | None = None,
    in_form: bool = False,
) -> None:
    """Start adding an action of `action_type` (`index` is `None`) or changing the one at `index`.

    For the actions that have no screen of their own - role and message actions do, see `action_screens`.
    Deleting the message has nothing to configure and is added right away - together with a restriction to
    moderators if the item has none yet, as otherwise everybody could use it. Opening a form creates the form that
    belongs to this action (it asks for its title first) and hands it to `open_form`, which shows its screen;
    changing such an action goes to that screen right away. `in_form` marks the actions of a form itself, which
    cannot open another form.
    """
    if action_type in ROLE_ACTIONS or action_type in MESSAGE_ACTIONS:
        raise ValueError(f"{action_type} is edited on a screen of its own")

    if index is None:
        # A form is the click's first answer, so it can neither be combined with other actions nor follow them.
        has_form = any(action.type is ActionType.OPEN_FORM for action in config.actions)
        if (action_type is ActionType.OPEN_FORM and config.actions) or (
            has_form and action_type is not ActionType.OPEN_FORM
        ):
            await after(interaction, problem_text(language, ConfigProblem.FORM_NOT_ALONE))
            return

    if action_type is ActionType.OPEN_FORM:
        await _open_form_action(interaction, language, config, inherited, index, after, library, open_form, in_form)
        return

    if len(config.actions) >= MAX_ACTIONS_PER_ITEM:
        await after(interaction, problem_text(language, ConfigProblem.TOO_MANY_ACTIONS, max=MAX_ACTIONS_PER_ITEM))
        return
    if any(action.type is action_type for action in config.actions):
        await after(interaction, problem_text(language, ConfigProblem.DUPLICATE_ACTION))
        return

    needs_restriction = action_type is ActionType.DELETE_MESSAGE and not is_restricted([*config.conditions, *inherited])
    if needs_restriction and len(config.conditions) >= MAX_CONDITIONS_PER_ITEM:
        # No room for the restriction the action needs: the user has to free a place first.
        await after(interaction, problem_text(language, ConfigProblem.DELETE_WITHOUT_RESTRICTION))
        return

    config.actions.append(Action(action_type))
    if needs_restriction:
        config.conditions.append(Condition(ConditionType.PERMISSIONS, permissions=DEFAULT_MOD_PERMISSIONS))
    await after(interaction, None)


async def _open_form_action(
    interaction: Interaction,
    language: SupportedLanguage,
    config: ItemConfig,
    inherited: Sequence[Condition],
    index: int | None,
    after: AfterEdit,
    library: InteractiveLibrary | None,
    open_form: AfterForm | None,
    in_form: bool,
) -> None:
    """Add an "open form" action together with the new form it opens, or go to the form of an existing one."""
    if in_form:
        await after(interaction, problem_text(language, ConfigProblem.NESTED_FORM))
        return
    if library is None or open_form is None:
        await after(interaction, t(language, "errors.form_gone"))
        return

    if index is not None:
        form = library.get(config.actions[index].form_id or 0)
        if form is None or not form.is_form:
            await after(interaction, t(language, "errors.form_gone"))
            return
        await open_form(interaction, form)
        return

    # Look for problems before asking for a title: the action is checked as if it already had its form.
    probe = [*config.actions, Action(ActionType.OPEN_FORM, form_id=0)]
    problems = validate_config(replace(config, actions=probe), inherited=inherited)
    if problems:
        await after(interaction, problem_text(language, problems[0], max=MAX_ACTIONS_PER_ITEM))
        return

    async def created(modal_interaction: Interaction, form_id: int | None, error: str | None) -> None:
        """Attach the new form to the item as its action and show the form's screen."""
        created_form = library.get(form_id) if form_id is not None else None
        if error is not None or created_form is None:
            await after(modal_interaction, error)
            return
        config.actions.append(Action(ActionType.OPEN_FORM, form_id=created_form.id))
        await open_form(modal_interaction, created_form)

    await interaction.response.send_modal(FormLookModal(language, library, None, created))


async def open_condition_editor(
    interaction: Interaction,
    language: SupportedLanguage,
    config: ItemConfig,
    inherited: Sequence[Condition],
    condition_type: ConditionType,
    index: int | None,
    after: AfterEdit,
    *,
    below: Sequence[ItemConfig] = (),
) -> None:
    """Start adding a restriction of `condition_type` (`index` is `None`) or changing the one at `index`. `below` are
    the configs of the options of a dropdown whose restrictions are edited: their actions must fit them too.

    "Once per person" has nothing to configure and is added right away; all others open their modal.
    """
    if index is None and len(config.conditions) >= MAX_CONDITIONS_PER_ITEM:
        await after(interaction, problem_text(language, ConfigProblem.TOO_MANY_CONDITIONS))
        return

    if condition_type is not ConditionType.ONCE_PER_USER:
        modal = ConditionModal(
            language, config, interaction.guild, condition_type, index, after, inherited=inherited, dependents=below
        )
        await interaction.response.send_modal(modal)
        return

    config.conditions.append(Condition(ConditionType.ONCE_PER_USER))
    problems = validate_config(config, inherited=inherited)
    if problems:
        config.conditions.pop()
    await after(interaction, problem_text(language, problems[0]) if problems else None)


def delete_condition(
    language: SupportedLanguage, config: ItemConfig, inherited: Sequence[Condition], index: int
) -> str | None:
    """Remove the restriction at `index`. Returns an error text, and keeps it, if the item still needs it - an item
    that deletes the message must stay limited to chosen people."""
    removed = config.conditions.pop(index)
    problems = validate_config(config, inherited=inherited)
    if problems:
        config.conditions.insert(index, removed)
        return problem_text(language, problems[0])
    return None


def _form_config(form: ItemDraft) -> FormConfig:
    """A form draft as the configuration that is stored and validated."""
    return FormConfig(
        title=form.label or "", questions=form.questions, actions=form.config.actions, conditions=form.config.conditions
    )


def _conflicting_actions(language: SupportedLanguage, draft: ItemDraft, library: InteractiveLibrary) -> str | None:
    """The error for the first item among the draft and the forms it opens whose actions contradict each other or the
    conditions they run under (an option's include those of its dropdown), or `None`. The screens do not let this
    happen - this catches what an older template may hold."""
    for item in (draft, *library.referenced_forms([draft])):
        scopes: list[tuple[ItemConfig, Sequence[Condition]]] = [(item.config, [])]
        scopes += [(option.config, item.config.conditions) for option in item.options]
        for config, inherited in scopes:
            if action_conflicts(config.actions) or condition_conflicts(config.actions, [*config.conditions, *inherited]):
                return t(language, "errors.actions_conflict", name=draft_name(language, item))
    return None


def sendable_problem(language: SupportedLanguage, drafts: Sequence[ItemDraft], library: InteractiveLibrary) -> str | None:
    """Why the message cannot be sent with these placed items, or `None`: actions that contradict each other, a
    dropdown without options, a form that is incomplete, or a dropdown that opens a form but lets several options be
    picked at once (only one form fits)."""
    for draft in drafts:
        conflict = _conflicting_actions(language, draft, library)
        if conflict is not None:
            return conflict
        for form in library.referenced_forms([draft]):
            if validate_form_config(_form_config(form)):
                return t(language, "errors.form_incomplete", name=draft_name(language, form))
        if draft.is_select and draft.selection_range()[1] > 1 and draft.referenced_form_ids():
            return t(language, "errors.form_needs_single_choice", name=draft_name(language, draft))

        if draft.is_select and not draft.options:
            return t(language, "errors.select_without_options", name=draft_name(language, draft))
        if draft.is_select and draft.mode is SelectMode.ROLES and any(option.role_id is None for option in draft.options):
            return t(language, "errors.select_without_options", name=draft_name(language, draft))
    return None


def move_option(draft: ItemDraft, option: OptionDraft, offset: int) -> None:
    """Move an option up (`-1`) or down (`1`) among the options of its dropdown."""
    index = draft.options.index(option)
    target = index + offset
    if 0 <= target < len(draft.options):
        draft.options[index], draft.options[target] = draft.options[target], draft.options[index]
