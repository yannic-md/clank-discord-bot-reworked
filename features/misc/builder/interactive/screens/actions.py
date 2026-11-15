from discord import Interaction, SelectOption

from features.misc.builder.interactive.action_screens import adding_problem
from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.editor import action_group_options, action_name, describe_action
from features.misc.builder.interactive.hub import option_name
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.modals import AfterEdit
from features.misc.builder.interactive.models import (
    MAX_ACTIONS_PER_ITEM,
    MESSAGE_ACTIONS,
    ROLE_ACTIONS,
    ActionType,
)
from features.misc.builder.interactive.screens.common import (
    back_to_element,
    bullet,
    clamp,
    item_scope,
    list_body,
    swap,
    switch_dropdown,
)
from features.misc.builder.interactive.screens.controls import (
    back_button,
    delete_button,
    down_button,
    dropdown,
    edit_button,
    up_button,
)
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen
from features.misc.builder.interactive.ui import open_action_editor


def actions_screen(
    host: Host,
    item_id: int,
    *,
    option_key: str | None = None,
    active_index: int | None = None,
    error: str | None = None,
) -> Screen:
    """Lists the actions of one button (or dropdown option) and lets the user add, change, delete and reorder them.

    `option_key` is the option of a dropdown whose actions these are (or `None` for a button), `active_index` the
    selected action."""
    session = host.session
    language = session.language

    draft, config, inherited = item_scope(session, item_id, option_key)
    actions = config.actions
    active = clamp(active_index, len(actions))

    option = draft.option(option_key) if option_key is not None else None
    entries = [
        f"{bullet(number == active)} {number + 1}. {describe_action(language, action, session.library)}"
        for number, action in enumerate(actions)
    ]
    description = "actions.description_form" if draft.is_form else "actions.description"
    page = Screen(
        screen(language, "actions.title_option", name=option_name(option))
        if option is not None
        else screen(language, "actions.title"),
        list_body(screen(language, description), screen(language, "actions.list"), entries),
    )

    def after_for(index: int | None) -> AfterEdit:
        """The callback that shows this screen again once a modal is done, with `index` selected."""

        async def after(interaction: Interaction, problem: str | None) -> None:
            """Show this screen again once a modal is done, with `index` selected."""
            await host.actions(interaction, item_id, option_key=option_key, active_index=index, error=problem)

        return after

    async def open_form(interaction: Interaction, form: ItemDraft) -> None:
        """Show the screen of a form - the one this action opens, or one that was just created for it."""
        await host.form(interaction, form.id)

    async def edit_action(interaction: Interaction, action_type: ActionType, index: int | None) -> None:
        """Start adding an action of `action_type` (`index` is `None`) or changing the one at `index`."""
        await open_action_editor(
            interaction,
            language,
            config,
            inherited,
            action_type,
            index,
            after_for(len(actions) if index is None else index),
            library=session.library,
            open_form=open_form,
            in_form=draft.is_form,
        )

    async def on_edit(interaction: Interaction) -> None:
        """Open the screen (or modal) to change the selected action."""
        assert active is not None
        action_type = actions[active].type
        if action_type in ROLE_ACTIONS:
            await host.role_action(interaction, item_id, option_key=option_key, index=active)
            return
        if action_type in MESSAGE_ACTIONS:
            await host.message_action(interaction, item_id, option_key=option_key, index=active)
            return
        await edit_action(interaction, action_type, active)

    async def on_delete(interaction: Interaction) -> None:
        """Delete the selected action."""
        assert active is not None
        del actions[active]
        session.library.prune_forms()
        await host.actions(interaction, item_id, option_key=option_key, active_index=active)

    async def on_up(interaction: Interaction) -> None:
        """Move the selected action one position up."""
        assert active is not None and active > 0
        swap(actions, active, -1)
        await host.actions(interaction, item_id, option_key=option_key, active_index=active - 1)

    async def on_down(interaction: Interaction) -> None:
        """Move the selected action one position down."""
        assert active is not None and active < len(actions) - 1
        swap(actions, active, 1)
        await host.actions(interaction, item_id, option_key=option_key, active_index=active + 1)

    async def on_switch(interaction: Interaction, value: str) -> None:
        """Select another action."""
        await host.actions(interaction, item_id, option_key=option_key, active_index=int(value))

    async def on_add(interaction: Interaction, values: list[str]) -> None:
        """Start adding the chosen kind of action: roles and messages have a screen of their own."""
        group = values[0]
        if group in ("roles", "message"):
            problem = adding_problem(language, config, group)
            if problem is not None:
                await after_for(active)(interaction, problem)
                return
            if group == "roles":
                await host.role_action(interaction, item_id, option_key=option_key)
            else:
                await host.message_action(interaction, item_id, option_key=option_key)
            return

        await edit_action(interaction, ActionType(group), None)

    # Deleting the message has nothing to change in it, so there is nothing to edit either.
    editable = active is not None and actions[active].type is not ActionType.DELETE_MESSAGE
    page.add(0, back_button(language, back_to_element(host, draft, item_id, option_key)))
    page.add(0, edit_button(language, on_edit, disabled=not editable))
    page.add(0, delete_button(language, on_delete, disabled=active is None))
    if len(actions) > 1:  # moving an action needs another one to move past
        page.add(0, up_button(language, on_up, disabled=active is None or active <= 0))
        page.add(0, down_button(language, on_down, disabled=active is None or active >= len(actions) - 1))

    switch_options = [
        SelectOption(
            label=f"{number + 1}. {action_name(language, action.type, len(action.roles))}"[:100],
            value=str(number),
            default=number == active,
        )
        for number, action in enumerate(actions)
    ]
    page.add(
        1,
        switch_dropdown(
            switch_options,
            screen(language, "placeholders.switch_action" if actions else "placeholders.no_actions"),
            on_switch,
        ),
    )

    full = len(actions) >= MAX_ACTIONS_PER_ITEM
    page.add(
        2,
        dropdown(
            "add",
            on_add,
            options=action_group_options(language, exclude={"open_form"} if draft.is_form else ()),
            placeholder=screen(language, "placeholders.add_action_full" if full else "placeholders.add_action"),
            disabled=full,
        ),
    )
    page.error = error
    return page
