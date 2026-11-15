from discord import ButtonStyle, Interaction

from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.editor import draft_sections
from features.misc.builder.interactive.hub import (
    delete_label,
    element_after,
    element_kinds,
    element_options,
    form_description,
    form_title,
    hub_text,
    hub_title,
    item_description,
    item_title,
    kind_options,
    kind_view_text,
    order_group,
    overview_text,
    start_element,
)
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.modals import AfterButton, ButtonModal, FormLookModal, SelectLookModal
from features.misc.builder.interactive.render import preview_component
from features.misc.builder.interactive.screens.controls import (
    Callback,
    actions_button,
    add_button,
    back_button,
    button,
    conditions_button,
    down_button,
    dropdown,
    look_button,
    preview,
    up_button,
)
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen


def after_button(host: Host) -> AfterButton:
    """What happens once a button modal is done: show the overview with that element selected."""

    async def after(interaction: Interaction, item_id: int | None, error: str | None) -> None:
        """Show the screen that follows a finished modal."""
        if item_id is not None:
            host.session.active_item_id = item_id
        await host.hub(interaction, error=error)

    return after


def after_create(host: Host) -> AfterButton:
    """What happens once the modal of a new element is done: show the element - or, if the modal refused it, the
    screen the user asked from, with the reason."""

    async def after(interaction: Interaction, item_id: int | None, error: str | None) -> None:
        """Show the screen that follows a finished modal."""
        if error is not None or item_id is None:
            await host.kinds(interaction, error=error)
            return
        host.session.active_item_id = item_id
        await host.hub(interaction)

    return after


def hub_screen(host: Host, *, error: str | None = None) -> Screen:
    """The "Buttons & Dropdowns" screen: a dropdown with the clickable elements and a button to create more. While
    nothing is selected it explains what the screen is for; with an element selected it shows just that element."""
    session = host.session
    language = session.language
    library = session.library

    active = library.get(session.active_item_id) if session.active_item_id is not None else None
    if active is not None and active.is_form:  # a form is changed through the action that opens it
        active = None
    session.active_item_id = active.id if active else None

    if active is None:
        page = Screen(
            hub_title(language),
            overview_text(language, webhook=session.webhook.enabled),
            warning=session.webhook.enabled,
        )
    else:
        # How the element looks is not in the summary: the element itself is shown next to the "Place" button.
        page = Screen(
            item_title(language, active),
            item_description(language, active, preview=True),
            sections=draft_sections(language, active, placement=host.placement_text(active.id), library=library),
            gap=2,
            spaced=False,
        )

    _add_navigation(host, page, active)
    if active is not None:
        _add_edit_row(host, page, active)
    if library.elements():
        _add_element_row(host, page, active)
    if active is not None:
        _add_place_row(host, page, active)
    page.error = error
    return page


def _look_callback(host: Host, active: ItemDraft) -> Callback:
    """The callback that opens the modal to change how the element looks (a dropdown: placeholder and limits)."""
    language = host.session.language
    library = host.session.library

    async def on_look(interaction: Interaction) -> None:
        """Open the modal to change how the element looks."""
        if active.is_select:
            await interaction.response.send_modal(SelectLookModal(language, active, after_button(host)))
            return
        await interaction.response.send_modal(ButtonModal(language, library, active.kind, active, after_button(host)))

    return on_look


def _add_navigation(host: Host, page: Screen, active: ItemDraft | None) -> None:
    """The first row. Without a selection: back to the main screen and add an element. With one: back to the
    overview, delete that element and - if there are several - move it up or down."""
    session = host.session
    language = session.language
    library = session.library

    def is_placed(item_id: int) -> bool:
        """Whether the element sits in the message."""
        return bool(host.placement_text(item_id))

    async def on_back(interaction: Interaction) -> None:
        """Go back: from a selected element to the overview, from the overview to the main screen."""
        if active is None:
            await host.main(interaction)
            return
        session.active_item_id = None
        await host.hub(interaction)

    async def on_create(interaction: Interaction) -> None:
        """Ask which kind of element to add."""
        await host.kinds(interaction)

    async def on_delete(interaction: Interaction) -> None:
        """Delete the selected element, also from the message. The next element is selected then; the overview
        shows only if there is none."""
        assert active is not None
        following = element_after(library, active.id, is_placed)
        host.delete_item(active.id)
        session.active_item_id = following
        await host.hub(interaction)

    def mover(offset: int) -> Callback:
        """The callback that moves the selected element by `offset` places in its list."""

        async def on_move(interaction: Interaction) -> None:
            """Move the selected element among those in the same state and show the screen again."""
            assert active is not None
            siblings = order_group(library, active, is_placed)
            target = [sibling.id for sibling in siblings].index(active.id) + offset
            if 0 <= target < len(siblings):
                library.swap(active.id, siblings[target].id)
            await host.hub(interaction)

        return on_move

    page.add(0, back_button(language, on_back))
    if active is None:
        page.add(0, add_button(hub_text(language, "create_button"), on_create, name="create", disabled=library.is_full))
        return

    if active.is_link:  # a link button has no actions or conditions, so its look has the first row to itself
        page.add(0, look_button(language, _look_callback(host, active)))
    page.add(0, button("delete", on_delete, label=delete_label(language, active), style=ButtonStyle.red, emoji="🗑️"))
    group = order_group(library, active, is_placed)
    if len(group) > 1:
        position = [draft.id for draft in group].index(active.id)
        page.add(0, up_button(language, mover(-1), disabled=position == 0))
        page.add(0, down_button(language, mover(1), disabled=position == len(group) - 1))


def _add_edit_row(host: Host, page: Screen, active: ItemDraft) -> None:
    """The row with what can be done to the selected element: change its look, set its actions or options and
    restrict it. A link button has neither, so it has no such row: its look sits in the first row."""
    session = host.session
    language = session.language
    if active.is_link:
        return

    async def on_inner(interaction: Interaction) -> None:
        """Open the list of the button's actions - or of the dropdown's options."""
        if active.is_select:
            await host.options(interaction, active.id)
            return
        await host.actions(interaction, active.id)

    async def on_conditions(interaction: Interaction) -> None:
        """Open the list of the element's restrictions."""
        await host.conditions(interaction, active.id)

    page.add(1, look_button(language, _look_callback(host, active)))
    page.add(
        1,
        button(
            "inner",
            on_inner,
            label=screen(language, "buttons.options" if active.is_select else "buttons.actions"),
            style=ButtonStyle.gray,
            emoji="🧩" if active.is_select else "⚙️",
        ),
    )
    page.add(1, conditions_button(language, on_conditions))


def _add_element_row(host: Host, page: Screen, active: ItemDraft | None) -> None:
    """The dropdown of the clickable elements - there is none while no element exists."""
    session = host.session
    language = session.language

    async def on_select(interaction: Interaction, values: list[str]) -> None:
        """Select an element to see and change it."""
        session.active_item_id = int(values[0])
        await host.hub(interaction)

    options = element_options(
        language,
        session.library,
        active_id=active.id if active is not None else None,
        is_placed=lambda item_id: bool(host.placement_text(item_id)),
        place_of=host.placement_label,
    )
    page.add(2, dropdown("elements", on_select, options=options, placeholder=hub_text(language, "elements.placeholder")))


def _add_place_row(host: Host, page: Screen, active: ItemDraft) -> None:
    """The button to place the selected element in the message. It sits below the dropdown, as it is the step
    that matters most, with the element itself - always disabled - to its left. A dropdown has no preview: a second
    dropdown on the screen would only be confusing, and it is listed with its options anyway."""
    language = host.session.language

    async def on_place(interaction: Interaction) -> None:
        """Open the screen to place the element in the message."""
        await host.placement(interaction, active.id)

    if not active.is_select:
        page.add(3, preview("preview", preview_component(active)))
    page.add(3, button("place", on_place, label=screen(language, "buttons.place"), style=ButtonStyle.green, emoji="📍"))


async def create_element(host: Host, interaction: Interaction, kind: str) -> None:
    """Start creating a clickable element: the modal for how it looks opens (see `start_element`)."""
    session = host.session
    await start_element(interaction, session.language, session.library, kind, after_create(host))


def kinds_screen(host: Host, *, error: str | None = None) -> Screen:
    """Asks which kind of clickable element to create: a link button, a button or a dropdown. With a custom sender
    only link buttons are on offer, and the screen says so."""
    session = host.session
    language = session.language
    webhook = session.webhook.enabled

    async def on_back(interaction: Interaction) -> None:
        """Go back to the overview."""
        await host.hub(interaction)

    async def on_select(interaction: Interaction, values: list[str]) -> None:
        """Create an element of the chosen kind."""
        await create_element(host, interaction, values[0])

    page = Screen(hub_text(language, "kind_view.title"), kind_view_text(language, webhook=webhook), warning=webhook)
    page.add(0, back_button(language, on_back))
    page.add(
        1,
        dropdown(
            "kind",
            on_select,
            options=kind_options(language, element_kinds(webhook=webhook)),
            placeholder=hub_text(language, "kind_view.placeholder"),
        ),
    )
    page.error = error
    return page


def form_screen(host: Host, form_id: int, *, error: str | None = None) -> Screen:
    """Everything about one form: its title, its questions, what happens once it is submitted and who may use it.
    A form belongs to the action of a button (or dropdown option) that opens it."""
    session = host.session
    language = session.language
    library = session.library

    form = library.get(form_id)
    assert form is not None and form.is_form

    async def on_back(interaction: Interaction) -> None:
        """Go back to the actions of the button (or option) that opens the form."""
        owner = library.form_owner(form_id)
        if owner is None:
            await host.hub(interaction)
            return
        draft, option_key = owner
        await host.actions(interaction, draft.id, option_key=option_key, active_index=0)

    async def after_title(interaction: Interaction, _item_id: int | None, problem: str | None) -> None:
        """Show the form again once its title was changed."""
        await host.form(interaction, form_id, error=problem)

    async def on_title(interaction: Interaction) -> None:
        """Open the modal to change the title of the form."""
        await interaction.response.send_modal(FormLookModal(language, library, form, after_title))

    async def on_questions(interaction: Interaction) -> None:
        """Open the list of the form's questions."""
        await host.questions(interaction, form_id)

    async def on_actions(interaction: Interaction) -> None:
        """Open the list of the actions that run once the form is submitted."""
        await host.actions(interaction, form_id)

    async def on_conditions(interaction: Interaction) -> None:
        """Open the list of the form's restrictions."""
        await host.conditions(interaction, form_id)

    page = Screen(
        form_title(language),
        form_description(language, form),
        sections=draft_sections(language, form, placement=None, library=library),
    )
    page.add(0, back_button(language, on_back))
    page.add(
        0,
        button("title", on_title, label=screen(language, "buttons.form_title"), style=ButtonStyle.blurple, emoji="✏️"),
    )
    page.add(
        0, button("questions", on_questions, label=screen(language, "buttons.questions"), style=ButtonStyle.gray, emoji="❓")
    )
    page.add(1, actions_button(language, on_actions))
    page.add(1, conditions_button(language, on_conditions))
    page.error = error
    return page
