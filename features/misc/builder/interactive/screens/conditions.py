from discord import Interaction, SelectOption

from features.misc.builder.interactive.editor import condition_type_options, describe_condition
from features.misc.builder.interactive.hub import option_name
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.messages import t as shared_t
from features.misc.builder.interactive.modals import AfterEdit
from features.misc.builder.interactive.models import MAX_CONDITIONS_PER_ITEM, ConditionType
from features.misc.builder.interactive.screens.common import (
    back_to_element,
    bullet,
    clamp,
    item_scope,
    list_body,
    switch_dropdown,
)
from features.misc.builder.interactive.screens.controls import back_button, delete_button, dropdown, edit_button
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen
from features.misc.builder.interactive.ui import delete_condition, dependent_configs, open_condition_editor


def conditions_screen(
    host: Host,
    item_id: int,
    *,
    option_key: str | None = None,
    active_index: int | None = None,
    error: str | None = None,
) -> Screen:
    """Lists the restrictions of one item (a dropdown option, or the dropdown as a whole) and lets the user add,
    change and delete them.

    `option_key` is the option of a dropdown whose restrictions these are (or `None` for a button or the dropdown as a
    whole), `active_index` the selected restriction."""
    language = host.session.language

    draft, config, inherited = item_scope(host.session, item_id, option_key)
    conditions = config.conditions
    active = clamp(active_index, len(conditions))

    option = draft.option(option_key) if option_key is not None else None
    entries = [
        f"{bullet(number == active)} {describe_condition(language, condition)}"
        for number, condition in enumerate(conditions)
    ]
    page = Screen(
        screen(language, "conditions.title_option", name=option_name(option))
        if option is not None
        else screen(language, "conditions.title"),
        list_body(screen(language, "conditions.description"), screen(language, "conditions.list"), entries),
    )

    def after_for(index: int | None) -> AfterEdit:
        """The callback that shows this screen again once a modal is done, with `index` selected."""

        async def after(interaction: Interaction, problem: str | None) -> None:
            """Show this screen again once a modal is done, with `index` selected."""
            await host.conditions(interaction, item_id, option_key=option_key, active_index=index, error=problem)

        return after

    async def edit_condition(interaction: Interaction, condition_type: ConditionType, index: int | None) -> None:
        """Start adding a restriction of `condition_type` (`index` is `None`) or changing the one at `index`."""
        await open_condition_editor(
            interaction,
            language,
            config,
            inherited,
            condition_type,
            index,
            after_for(len(conditions) if index is None else index),
            below=dependent_configs(draft, option_key),
        )

    async def on_edit(interaction: Interaction) -> None:
        """Open the modal to change the selected restriction."""
        assert active is not None
        await edit_condition(interaction, conditions[active].type, active)

    async def on_delete(interaction: Interaction) -> None:
        """Delete the selected restriction - unless the item needs it."""
        assert active is not None
        problem = delete_condition(language, config, inherited, active)
        await host.conditions(interaction, item_id, option_key=option_key, active_index=active, error=problem)

    async def on_switch(interaction: Interaction, value: str) -> None:
        """Select another restriction."""
        await host.conditions(interaction, item_id, option_key=option_key, active_index=int(value))

    async def on_add(interaction: Interaction, values: list[str]) -> None:
        """Start adding the chosen restriction."""
        await edit_condition(interaction, ConditionType(values[0]), None)

    # "Once per person" has nothing to configure, so there is nothing to edit either.
    editable = active is not None and conditions[active].type is not ConditionType.ONCE_PER_USER
    page.add(0, back_button(language, back_to_element(host, draft, item_id, option_key)))
    page.add(0, edit_button(language, on_edit, disabled=not editable))
    page.add(0, delete_button(language, on_delete, disabled=active is None))

    switch_options = [
        SelectOption(
            label=shared_t(language, f"editor.condition_name.{condition.type.value}")[:100],
            value=str(number),
            default=number == active,
        )
        for number, condition in enumerate(conditions)
    ]
    page.add(
        1,
        switch_dropdown(
            switch_options,
            screen(language, "placeholders.switch_condition" if conditions else "placeholders.no_conditions"),
            on_switch,
        ),
    )

    add_options = condition_type_options(language, {condition.type for condition in conditions})
    limit_reached = len(conditions) >= MAX_CONDITIONS_PER_ITEM
    if limit_reached:
        add_placeholder = "placeholders.add_condition_limit"
    elif add_options:
        add_placeholder = "placeholders.add_condition"
    else:
        add_placeholder = "placeholders.add_condition_full"
    page.add(
        2,
        dropdown(
            "add",
            on_add,
            options=add_options,
            placeholder=screen(language, add_placeholder),
            disabled=limit_reached or not add_options,
        ),
    )
    page.error = error
    return page
