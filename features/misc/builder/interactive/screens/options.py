from discord import Interaction, SelectOption

from core.discord_api.limits import MAX_SELECT_ITEMS
from features.misc.builder.interactive.editor import describe_option
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.modals import AfterOption, OptionModal, RoleOptionsModal
from features.misc.builder.interactive.models import SelectMode
from features.misc.builder.interactive.screens.common import bullet, list_body, switch_dropdown
from features.misc.builder.interactive.screens.controls import (
    actions_button,
    add_button,
    back_button,
    conditions_button,
    delete_button,
    down_button,
    look_button,
    up_button,
)
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen
from features.misc.builder.interactive.ui import move_option


def options_screen(host: Host, item_id: int, *, active_key: str | None = None, error: str | None = None) -> Screen:
    """Lists the options of one dropdown and lets the user add, restyle, delete and reorder them - and, in a
    dropdown of texts, open the actions and restrictions of the selected one."""
    session = host.session
    language = session.language

    draft = session.library.get(item_id)
    assert draft is not None
    options = draft.options
    active = draft.option(active_key) if active_key is not None else None
    if active is None and options:
        active = options[0]
    roles_mode = draft.mode is SelectMode.ROLES

    entries = [
        f"{bullet(option is active)} {number}. {describe_option(language, draft, option)}"
        for number, option in enumerate(options, 1)
    ]
    page = Screen(
        screen(language, "options.title"),
        list_body(screen(language, "options.description." + draft.mode.value), screen(language, "options.list"), entries),
    )

    def after_option() -> AfterOption:
        """The callback that shows the option list again once a modal is done."""

        async def after(interaction: Interaction, key: str | None, problem: str | None) -> None:
            """Show the option list again with the changed option selected."""
            await host.options(interaction, item_id, active_key=key or active_key, error=problem)

        return after

    async def on_back(interaction: Interaction) -> None:
        """Go back to the item list."""
        await host.hub(interaction)

    async def on_add(interaction: Interaction) -> None:
        """Open the modal to add an option (a role dropdown: to pick the roles to add)."""
        if roles_mode:
            await interaction.response.send_modal(RoleOptionsModal(language, draft, after_option()))
            return
        await interaction.response.send_modal(OptionModal(language, draft, None, after_option()))

    async def on_look(interaction: Interaction) -> None:
        """Open the modal to change how the selected option looks."""
        assert active is not None
        await interaction.response.send_modal(OptionModal(language, draft, active, after_option()))

    async def on_delete(interaction: Interaction) -> None:
        """Delete the selected option."""
        assert active is not None
        draft.options.remove(active)
        session.library.prune_forms()
        await host.options(interaction, item_id)

    async def on_actions(interaction: Interaction) -> None:
        """Open the list of the selected option's actions."""
        assert active is not None
        await host.actions(interaction, item_id, option_key=active.key)

    async def on_conditions(interaction: Interaction) -> None:
        """Open the list of the selected option's restrictions."""
        assert active is not None
        await host.conditions(interaction, item_id, option_key=active.key)

    async def on_up(interaction: Interaction) -> None:
        """Move the selected option one position up."""
        assert active is not None
        move_option(draft, active, -1)
        await host.options(interaction, item_id, active_key=active.key)

    async def on_down(interaction: Interaction) -> None:
        """Move the selected option one position down."""
        assert active is not None
        move_option(draft, active, 1)
        await host.options(interaction, item_id, active_key=active.key)

    async def on_switch(interaction: Interaction, key: str) -> None:
        """Select another option."""
        await host.options(interaction, item_id, active_key=key)

    # Only what can be used is shown: a button that would be disabled is not there, so that the screen does not
    # overwhelm. The dropdown stays, empty or not, as it shows the options.
    page.add(0, back_button(language, on_back))
    if len(options) < MAX_SELECT_ITEMS:
        page.add(0, add_button(screen(language, "buttons.option_add"), on_add))
    if active is not None:
        page.add(0, delete_button(language, on_delete))

    position = options.index(active) if active is not None else None
    if active is not None:  # how the option looks sits with what else can be set on it
        page.add(1, look_button(language, on_look))
    if active is not None and not roles_mode:  # the options of a role dropdown have no actions or restrictions
        page.add(1, actions_button(language, on_actions))
        page.add(1, conditions_button(language, on_conditions))
    if position is not None and position > 0:
        page.add(1, up_button(language, on_up))
    if position is not None and position < len(options) - 1:
        page.add(1, down_button(language, on_down))

    switch_options = [
        SelectOption(
            label=f"{number}. {option.label}"[:100],
            value=option.key,
            emoji=option.emoji,
            description=option.description[:100] if option.description else None,
            default=option is active,
        )
        for number, option in enumerate(options, 1)
    ]
    page.add(
        2,
        switch_dropdown(
            switch_options,
            screen(language, "placeholders.switch_option" if options else "placeholders.no_options"),
            on_switch,
        ),
    )
    page.error = error
    return page
