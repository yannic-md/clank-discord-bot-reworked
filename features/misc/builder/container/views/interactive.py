from collections.abc import Callable, Coroutine
from typing import Any

from discord import ButtonStyle, Colour, Interaction, Member, Role, SelectOption
from discord.ui import ActionRow, ChannelSelect, Container, TextDisplay

from features.misc.builder.channels import can_post_in, resolve_selected_channel
from features.misc.builder.container.models import ComponentKind
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.placement import (
    NEW_ROW_MESSAGE_VALUE,
    PREVIEW_ROWS,
    delete_item,
    describe_placement,
    find_placement,
    has_placed_items,
    message_outline,
    move_in_row,
    place_item,
    placement_label,
    placement_options,
    preview_rows,
)
from features.misc.builder.container.views.base import (
    BuilderLayoutView,
    add_button,
    add_select,
    info_container,
    info_separator,
    sections_container,
    show,
)
from features.misc.builder.interactive.action_screens import (
    MESSAGE_TYPES,
    ROLE_TYPES,
    adding_problem,
    channel_select,
    chosen_role_problem,
    clash_problem,
    message_preview,
    message_sections,
    new_message_action,
    role_sections,
    role_select,
    save_action,
    screen_texts,
    type_options,
    variables_help,
    with_channel,
    with_payload,
    with_roles,
    with_type,
)
from features.misc.builder.interactive.draft import ItemDraft
from features.misc.builder.interactive.editor import (
    BULLET,
    BULLET_ACTIVE,
    action_group_options,
    action_name,
    condition_type_options,
    describe_action,
    describe_condition,
    describe_draft,
    describe_option,
    describe_question,
    draft_name,
    draft_sections,
)
from features.misc.builder.interactive.hub import (
    delete_label,
    element_after,
    element_kinds,
    element_name,
    element_options,
    form_description,
    form_title,
    hub_text,
    hub_title,
    item_description,
    item_title,
    kind_options,
    kind_view_text,
    option_name,
    order_group,
    overview_text,
    start_element,
)
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.messages import t as shared_t
from features.misc.builder.interactive.modals import (
    AfterButton,
    AfterEdit,
    AfterOption,
    AfterQuestion,
    ButtonModal,
    FormLookModal,
    MessageContentModal,
    OptionModal,
    QuestionModal,
    RoleOptionsModal,
    SelectLookModal,
)
from features.misc.builder.interactive.models import (
    MAX_ACTIONS_PER_ITEM,
    MAX_CONDITIONS_PER_ITEM,
    MAX_QUESTIONS_PER_FORM,
    MESSAGE_ACTIONS,
    ROLE_ACTIONS,
    Action,
    ActionType,
    ConditionType,
    MessagePayload,
    SelectMode,
)
from features.misc.builder.interactive.render import preview_component
from features.misc.builder.interactive.templates import load_template_choices
from features.misc.builder.interactive.ui import (
    delete_condition,
    dependent_configs,
    move_option,
    open_action_editor,
    open_condition_editor,
    scope_of,
)


def _after_button(session: ContainerBuilderSession) -> AfterButton:
    """What happens once a button modal is done: show the item list with that item selected."""

    async def after(interaction: Interaction, item_id: int | None, error: str | None) -> None:
        """Show the screen that follows a finished modal."""
        if item_id is not None:
            session.active_item_id = item_id
        await show(interaction, InteractiveHubView(session, error=error))

    return after


def _clamp(index: int | None, length: int) -> int | None:
    """`index` limited to the valid positions of a list with `length` entries (`None` for an empty list)."""
    if length == 0:
        return None
    return min(max(index or 0, 0), length - 1)


async def _create_element(session: ContainerBuilderSession, interaction: Interaction, kind: str) -> None:
    """Start creating a clickable element: the modal for how it looks opens (see `start_element`)."""
    await start_element(interaction, session.language, session.library, kind, _after_create(session))


def _after_create(session: ContainerBuilderSession) -> AfterButton:
    """What happens once the modal of a new element is done: show the element - or, if the modal refused it, the
    screen the user asked from, with the reason."""

    async def after(interaction: Interaction, item_id: int | None, error: str | None) -> None:
        """Show the screen that follows a finished modal."""
        if error is not None or item_id is None:
            await show(interaction, ElementKindView(session, error=error))
            return
        session.active_item_id = item_id
        await show(interaction, InteractiveHubView(session))

    return after


def _look_callback(session: ContainerBuilderSession, active: ItemDraft) -> Callable[[Interaction], Coroutine[Any, Any, Any]]:
    """The callback that opens the modal to change how the element looks (a dropdown: placeholder and limits)."""
    language = session.language

    async def on_look(interaction: Interaction) -> None:
        """Open the modal to change how the element looks."""
        if active.is_select:
            await interaction.response.send_modal(SelectLookModal(language, active, _after_button(session)))
            return
        await interaction.response.send_modal(
            ButtonModal(language, session.library, active.kind, active, _after_button(session))
        )

    return on_look


class InteractiveHubView(BuilderLayoutView):
    """The "Buttons & Dropdowns" screen: a dropdown with the clickable elements and a button to create more. While
    nothing is selected it explains what the screen is for; with an element selected it shows just that element."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language
        library = session.library

        active = library.get(session.active_item_id) if session.active_item_id is not None else None
        if active is not None and active.is_form:  # a form is changed through the action that opens it
            active = None
        session.active_item_id = active.id if active else None

        if active is None:
            text = f"### {hub_title(language)}\n{overview_text(language, webhook=session.webhook.enabled)}"
            colour = Colour.orange() if session.webhook.enabled else Colour.blurple()
            self.add_item(Container(TextDisplay(text), accent_colour=colour))
        else:
            # How the element looks is not in the summary: the element itself is shown next to the "Place" button.
            placement = describe_placement(session, active.id)
            heading = f"### {item_title(language, active)}\n{item_description(language, active, preview=True)}"
            sections = draft_sections(language, active, placement=placement, library=library)
            self.add_item(sections_container(heading, sections, spaced=False))

        self._add_navigation(session, active)
        if active is not None:
            self._add_edit_row(session, active)
        if library.elements():
            self._add_element_row(session, active)
        if active is not None:
            self._add_place_row(session, active)

        if error:
            self.add_error(error)

    def _add_navigation(self, session: ContainerBuilderSession, active: ItemDraft | None) -> None:
        """The first row. Without a selection: back to the main screen and add an element. With one: back to the
        overview, delete that element and - if there are several - move it up or down."""
        from features.misc.builder.container.views.gui import MainView

        language = session.language
        library = session.library
        row: ActionRow = ActionRow()

        def is_placed(item_id: int) -> bool:
            """Whether the element sits in the message."""
            return bool(describe_placement(session, item_id))

        async def on_back(interaction: Interaction) -> None:
            """Go back: from a selected element to the overview, from the overview to the main screen."""
            if active is None:
                await show(interaction, MainView(session))
                return
            session.active_item_id = None
            await show(interaction, InteractiveHubView(session))

        async def on_create(interaction: Interaction) -> None:
            """Ask which kind of element to add."""
            await show(interaction, ElementKindView(session))

        async def on_delete(interaction: Interaction) -> None:
            """Delete the selected element, also from the message. The next element is selected then; the overview
            shows only if there is none."""
            assert active is not None
            following = element_after(library, active.id, is_placed)
            delete_item(session, active.id)
            session.active_item_id = following
            await show(interaction, InteractiveHubView(session))

        def mover(offset: int) -> Callable[[Interaction], Coroutine[Any, Any, Any]]:
            """The callback that moves the selected element by `offset` places in its list."""

            async def on_move(interaction: Interaction) -> None:
                """Move the selected element among those in the same state and show the screen again."""
                assert active is not None
                group = order_group(library, active, is_placed)
                target = [draft.id for draft in group].index(active.id) + offset
                if 0 <= target < len(group):
                    library.swap(active.id, group[target].id)
                await show(interaction, InteractiveHubView(session))

            return on_move

        add_button(row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        if active is None:
            add_button(
                row,
                on_create,
                label=hub_text(language, "create_button"),
                style=ButtonStyle.green,
                emoji="➕",
                disabled=library.is_full,
            )
        else:
            if active.is_link:  # a link button has no actions or conditions, so its look has the first row to itself
                add_button(
                    row,
                    _look_callback(session, active),
                    label=screen(language, "buttons.look"),
                    style=ButtonStyle.blurple,
                    emoji="✏️",
                )
            add_button(row, on_delete, label=delete_label(language, active), style=ButtonStyle.red, emoji="🗑️")
            group = order_group(library, active, is_placed)
            if len(group) > 1:
                position = [draft.id for draft in group].index(active.id)
                add_button(
                    row,
                    mover(-1),
                    label=ts(language, "buttons.up"),
                    style=ButtonStyle.blurple,
                    emoji="⬆️",
                    disabled=position == 0,
                )
                add_button(
                    row,
                    mover(1),
                    label=ts(language, "buttons.down"),
                    style=ButtonStyle.blurple,
                    emoji="⬇️",
                    disabled=position == len(group) - 1,
                )
        self.add_item(row)

    def _add_element_row(self, session: ContainerBuilderSession, active: ItemDraft | None) -> None:
        """The dropdown of the clickable elements - there is none while no element exists."""
        language = session.language
        options = element_options(
            language,
            session.library,
            active_id=active.id if active is not None else None,
            is_placed=lambda item_id: bool(describe_placement(session, item_id)),
            place_of=lambda item_id: placement_label(session, item_id),
        )

        async def on_select(interaction: Interaction) -> None:
            """Select an element to see and change it."""
            session.active_item_id = int(element_select.values[0])
            await show(interaction, InteractiveHubView(session))

        row: ActionRow = ActionRow()
        element_select = add_select(row, on_select, options=options, placeholder=hub_text(language, "elements.placeholder"))
        self.add_item(row)

    def _add_place_row(self, session: ContainerBuilderSession, active: ItemDraft) -> None:
        """The button to place the selected element in the message. It sits below the dropdown, as it is the step
        that matters most, with the element itself - always disabled - to its left. A dropdown has no preview: it is
        listed with its options anyway."""

        async def on_place(interaction: Interaction) -> None:
            """Open the screen to place the element in the message."""
            await show(interaction, PlacementView(session, active.id))

        row: ActionRow = ActionRow()
        if not active.is_select:
            row.add_item(preview_component(active))
        add_button(row, on_place, label=screen(session.language, "buttons.place"), style=ButtonStyle.green, emoji="📍")
        self.add_item(row)

    def _add_edit_row(self, session: ContainerBuilderSession, active: ItemDraft) -> None:
        """The row with what can be done to the selected element: change its look, set its actions or options and
        restrict it. A link button has neither, so it has no such row: its look sits in the first row."""
        language = session.language
        if active.is_link:
            return

        row: ActionRow = ActionRow()

        async def on_inner(interaction: Interaction) -> None:
            """Open the list of the button's actions - or of the dropdown's options."""
            if active.is_select:
                await show(interaction, OptionsView(session, active.id))
                return
            await show(interaction, ItemActionsView(session, active.id))

        async def on_conditions(interaction: Interaction) -> None:
            """Open the list of the element's restrictions."""
            await show(interaction, ItemConditionsView(session, active.id))

        add_button(
            row,
            _look_callback(session, active),
            label=screen(language, "buttons.look"),
            style=ButtonStyle.blurple,
            emoji="✏️",
        )
        add_button(
            row,
            on_inner,
            label=screen(language, "buttons.options" if active.is_select else "buttons.actions"),
            style=ButtonStyle.gray,
            emoji="🧩" if active.is_select else "⚙️",
        )
        add_button(row, on_conditions, label=screen(language, "buttons.conditions"), style=ButtonStyle.gray, emoji="🔒")
        self.add_item(row)


class ElementKindView(BuilderLayoutView):
    """Asks which kind of clickable element to create: a link button, a button or a dropdown. With a custom sender
    only link buttons are on offer, and the screen says so."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """Build the explanation and the dropdown of kinds; `error` is an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language
        webhook = session.webhook.enabled

        text = f"### {hub_text(language, 'kind_view.title')}\n{kind_view_text(language, webhook=webhook)}"
        colour = Colour.orange() if webhook else Colour.blurple()
        self.add_item(Container(TextDisplay(text), accent_colour=colour))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the overview."""
            await show(interaction, InteractiveHubView(session))

        async def on_select(interaction: Interaction) -> None:
            """Create an element of the chosen kind."""
            await _create_element(session, interaction, kind_select.values[0])

        nav_row: ActionRow = ActionRow()
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        kind_select = add_select(
            select_row,
            on_select,
            options=kind_options(language, element_kinds(webhook=webhook)),
            placeholder=hub_text(language, "kind_view.placeholder"),
        )
        self.add_item(select_row)

        if error:
            self.add_error(error)


class FormView(BuilderLayoutView):
    """Everything about one form: its title, its questions, what happens once it is submitted and who may use it.
    A form belongs to the action of a button (or dropdown option) that opens it."""

    def __init__(self, session: ContainerBuilderSession, form_id: int, *, error: str | None = None) -> None:
        """`form_id` is the form and `error` an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language
        library = session.library

        form = library.get(form_id)
        assert form is not None and form.is_form
        summary = describe_draft(language, form, placement=None, library=library)
        heading = f"### {form_title(language)}\n{form_description(language, form)}"
        self.add_item(Container(TextDisplay(f"{heading}\n\n{summary}"), accent_colour=Colour.blurple()))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the actions of the button (or option) that opens the form."""
            owner = library.form_owner(form_id)
            if owner is None:
                await show(interaction, InteractiveHubView(session))
                return
            draft, option_key = owner
            await show(interaction, ItemActionsView(session, draft.id, option_key=option_key, active_index=0))

        async def after_title(interaction: Interaction, _item_id: int | None, problem: str | None) -> None:
            """Show the form again once its title was changed."""
            await show(interaction, FormView(session, form_id, error=problem))

        async def on_title(interaction: Interaction) -> None:
            """Open the modal to change the title of the form."""
            await interaction.response.send_modal(FormLookModal(language, library, form, after_title))

        async def on_questions(interaction: Interaction) -> None:
            """Open the list of the form's questions."""
            await show(interaction, QuestionsView(session, form_id))

        async def on_actions(interaction: Interaction) -> None:
            """Open the list of the actions that run once the form is submitted."""
            await show(interaction, ItemActionsView(session, form_id))

        async def on_conditions(interaction: Interaction) -> None:
            """Open the list of the form's restrictions."""
            await show(interaction, ItemConditionsView(session, form_id))

        nav_row: ActionRow = ActionRow()
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(nav_row, on_title, label=screen(language, "buttons.form_title"), style=ButtonStyle.blurple, emoji="✏️")
        add_button(nav_row, on_questions, label=screen(language, "buttons.questions"), style=ButtonStyle.gray, emoji="❓")
        self.add_item(nav_row)

        row: ActionRow = ActionRow()
        add_button(row, on_actions, label=screen(language, "buttons.actions"), style=ButtonStyle.gray, emoji="⚙️")
        add_button(row, on_conditions, label=screen(language, "buttons.conditions"), style=ButtonStyle.gray, emoji="🔒")
        self.add_item(row)

        if error:
            self.add_error(error)


class PlacementView(BuilderLayoutView):
    """Lets the user choose where an item goes: a new row, a row with room, or next to a text. The screen stays open
    while the item is moved around, and shows the items that are placed. While nothing is placed yet and the message
    has just one place to offer, there is nothing to choose from, so the user is only asked whether to place the item
    at all."""

    def __init__(self, session: ContainerBuilderSession, item_id: int, *, error: str | None = None) -> None:
        """`item_id` is the item to place and `error` an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None

        header = f"### {screen(language, 'placement.title', name=element_name(language, draft))}"
        options = placement_options(session, draft)

        async def on_place(interaction: Interaction, target: str) -> None:
            """Put the item in the chosen place, or take it out of the message again - and show the result."""
            await show(interaction, PlacementView(session, item_id, error=place_item(session, draft, target)))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the item list."""
            await show(interaction, InteractiveHubView(session))

        if not has_placed_items(session) and [option.value for option in options] == [NEW_ROW_MESSAGE_VALUE]:
            self.add_item(info_container(f"{header}\n{screen(language, 'placement.confirm')}"))

            async def on_yes(interaction: Interaction) -> None:
                """Place the item in a row of its own."""
                await on_place(interaction, NEW_ROW_MESSAGE_VALUE)

            confirm_row: ActionRow = ActionRow()
            add_button(confirm_row, on_yes, label=ts(language, "buttons.yes"), style=ButtonStyle.green, emoji="✅")
            add_button(confirm_row, on_back, label=ts(language, "buttons.no"), style=ButtonStyle.red, emoji="🛑")
            self.add_item(confirm_row)
            if error:
                self.add_error(error)
            return

        placement = find_placement(session, item_id)
        rows = preview_rows(session)

        # What the screen is for and where a button may go; below a divider, the message the buttons are placed in: a
        # button can go anywhere in it, so what it is made of is what makes the places clear.
        explanation = f"{header}\n{screen(language, 'placement.description')}\n\n{t(language, 'info.placement.rows')}"
        box: Container = Container(TextDisplay(explanation), accent_colour=Colour.blurple())
        outline = message_outline(session, marked=item_id)
        if outline:
            notes = [f"**{t(language, 'info.placement.outline')}:**", outline]
            if placement is not None:
                notes += ["", t(language, "info.placement.marked")]
            if len(rows) > PREVIEW_ROWS:  # the screen has room to preview only some of the rows
                notes += ["", t(language, "info.placement.preview_truncated", shown=PREVIEW_ROWS, total=len(rows))]
            box.add_item(info_separator())
            box.add_item(TextDisplay("\n".join(notes)))
        self.add_item(box)

        nav_row: ActionRow = ActionRow()
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")

        # Two buttons in a row can swap places: the item moves along its row, one place at a time.
        in_row = placement is not None and placement.node.kind == ComponentKind.ACTION_ROW
        neighbours = placement.node.item_ids if placement is not None and in_row else []
        if len(neighbours) > 1:

            def mover(offset: int) -> Callable[[Interaction], Coroutine[Any, Any, None]]:
                """The callback that moves the item `offset` places along its row and shows the screen again."""

                async def move(interaction: Interaction) -> None:
                    """Move the item along its row."""
                    move_in_row(session, item_id, offset)
                    await show(interaction, PlacementView(session, item_id))

                return move

            position = neighbours.index(item_id)
            add_button(
                nav_row,
                mover(-1),
                label=ts(language, "buttons.left"),
                style=ButtonStyle.blurple,
                emoji="⬅️",
                disabled=position == 0,
            )
            add_button(
                nav_row,
                mover(1),
                label=ts(language, "buttons.right"),
                style=ButtonStyle.blurple,
                emoji="➡️",
                disabled=position == len(neighbours) - 1,
            )
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()

        async def on_select(interaction: Interaction) -> None:
            """Put the item in the chosen place."""
            value = target_select.values[0]
            if value == "__none__":
                return
            await on_place(interaction, value)

        target_select = add_select(
            select_row,
            on_select,
            options=options,
            placeholder=screen(language, "placeholders.placement_target" if options else "placeholders.placement_empty"),
            disabled=not options,
        )
        self.add_item(select_row)

        # The placed rows as the message shows them, below the dropdown.
        for row_drafts in rows[:PREVIEW_ROWS]:
            preview_row: ActionRow = ActionRow()
            for placed in row_drafts:
                preview_row.add_item(preview_component(placed))
            self.add_item(preview_row)

        if error:
            self.add_error(error)


class OptionsView(BuilderLayoutView):
    """Lists the options of one dropdown and lets the user add, restyle, delete and reorder them - and, in a
    dropdown of texts, open the actions and restrictions of the selected one."""

    def __init__(
        self, session: ContainerBuilderSession, item_id: int, *, active_key: str | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the dropdown, `active_key` the selected option and `error` an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        options = draft.options
        active = draft.option(active_key) if active_key is not None else None
        if active is None and options:
            active = options[0]
        roles_mode = draft.mode is SelectMode.ROLES

        header = f"### {screen(language, 'options.title')}"
        lines = [screen(language, "options.description." + draft.mode.value)]
        if options:
            lines += ["", f"**{screen(language, 'options.list')}:**"]
        for number, option in enumerate(options, 1):
            marker = BULLET_ACTIVE if option is active else BULLET
            lines.append(f"{marker} {number}. {describe_option(language, draft, option)}")
        self.add_item(info_container(header + "\n" + "\n".join(lines)))

        def after_option() -> AfterOption:
            """The callback that shows the option list again once a modal is done."""

            async def after(interaction: Interaction, key: str | None, problem: str | None) -> None:
                """Show the option list again with the changed option selected."""
                await show(interaction, OptionsView(session, item_id, active_key=key or active_key, error=problem))

            return after

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the item list."""
            await show(interaction, InteractiveHubView(session))

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
            await show(interaction, OptionsView(session, item_id))

        # Only what can be used is shown: a button that would be disabled is not there, so that the screen does not
        # overwhelm. The dropdown stays, empty or not, as it shows the options.
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        if len(options) < 25:
            add_button(nav_row, on_add, label=screen(language, "buttons.option_add"), style=ButtonStyle.green, emoji="➕")
        if active is not None:
            add_button(nav_row, on_delete, label=screen(language, "buttons.delete"), style=ButtonStyle.red, emoji="🗑️")
        self.add_item(nav_row)

        inner_row: ActionRow = ActionRow()

        async def on_actions(interaction: Interaction) -> None:
            """Open the list of the selected option's actions."""
            assert active is not None
            await show(interaction, ItemActionsView(session, item_id, option_key=active.key))

        async def on_conditions(interaction: Interaction) -> None:
            """Open the list of the selected option's restrictions."""
            assert active is not None
            await show(interaction, ItemConditionsView(session, item_id, option_key=active.key))

        async def on_up(interaction: Interaction) -> None:
            """Move the selected option one position up."""
            assert active is not None
            move_option(draft, active, -1)
            await show(interaction, OptionsView(session, item_id, active_key=active.key))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected option one position down."""
            assert active is not None
            move_option(draft, active, 1)
            await show(interaction, OptionsView(session, item_id, active_key=active.key))

        position = options.index(active) if active is not None else None
        if active is not None:  # how the option looks sits with what else can be set on it
            add_button(inner_row, on_look, label=screen(language, "buttons.look"), style=ButtonStyle.blurple, emoji="✏️")
        if active is not None and not roles_mode:  # the options of a role dropdown have no actions or restrictions
            add_button(inner_row, on_actions, label=screen(language, "buttons.actions"), style=ButtonStyle.gray, emoji="⚙️")
            add_button(
                inner_row, on_conditions, label=screen(language, "buttons.conditions"), style=ButtonStyle.gray, emoji="🔒"
            )
        if position is not None and position > 0:
            add_button(inner_row, on_up, label=ts(language, "buttons.up"), style=ButtonStyle.blurple, emoji="⬆️")
        if position is not None and position < len(options) - 1:
            add_button(inner_row, on_down, label=ts(language, "buttons.down"), style=ButtonStyle.blurple, emoji="⬇️")
        if inner_row.children:  # a row without a button is not allowed
            self.add_item(inner_row)

        switch_row: ActionRow = ActionRow()
        switch_options = [
            SelectOption(
                label=f"{number}. {option.label}"[:100],
                value=option.key,
                emoji=option.emoji,
                description=option.description[:100] if option.description else None,
                default=option is active,
            )
            for number, option in enumerate(options, 1)
        ] or [SelectOption(label="—", value="__none__")]

        async def on_switch(interaction: Interaction) -> None:
            """Select another option."""
            if not options:
                return
            await show(interaction, OptionsView(session, item_id, active_key=switch_select.values[0]))

        switch_select = add_select(
            switch_row,
            on_switch,
            options=switch_options,
            placeholder=screen(language, "placeholders.switch_option" if options else "placeholders.no_options"),
            disabled=not options,
        )
        self.add_item(switch_row)

        if error:
            self.add_error(error)


class ItemActionsView(BuilderLayoutView):
    """Lists the actions of one button (or dropdown option) and lets the user add, change, delete and reorder them."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown whose actions these are (or `None` for a
        button). `active_index` is the selected action and `error` an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        actions = config.actions
        active = _clamp(active_index, len(actions))

        option = draft.option(option_key) if option_key is not None else None
        title = screen(language, "actions.title_option", name=option_name(option)) if option is not None else None
        header = f"### {title or screen(language, 'actions.title')}"
        description = "actions.description_form" if draft.is_form else "actions.description"
        lines = [screen(language, description)]
        if actions:
            lines += ["", f"**{screen(language, 'actions.list')}:**"]
        for number, action in enumerate(actions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {number + 1}. {describe_action(language, action, session.library)}")
        self.add_item(info_container(header + "\n" + "\n".join(lines)))

        def after_for(index: int | None) -> AfterEdit:
            """The callback that shows this screen again once a modal is done, with `index` selected."""

            async def after(interaction: Interaction, problem: str | None) -> None:
                """Show this screen again once a modal is done, with `index` selected."""
                view = ItemActionsView(session, item_id, option_key=option_key, active_index=index, error=problem)
                await show(interaction, view)

            return after

        nav_row: ActionRow = ActionRow()

        async def open_form(interaction: Interaction, form: ItemDraft) -> None:
            """Show the screen of a form - the one this action opens, or one that was just created for it."""
            await show(interaction, FormView(session, form.id))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the form, the option list, or the item list for a button."""
            if draft.is_form:
                await show(interaction, FormView(session, item_id))
                return
            if option_key is not None:
                await show(interaction, OptionsView(session, item_id, active_key=option_key))
                return
            await show(interaction, InteractiveHubView(session))

        async def on_edit(interaction: Interaction) -> None:
            """Open the screen (or modal) to change the selected action."""
            assert active is not None
            action_type = actions[active].type
            if action_type in ROLE_ACTIONS:
                await show(interaction, RoleActionView(session, item_id, option_key=option_key, index=active))
                return
            if action_type in MESSAGE_ACTIONS:
                await show(interaction, MessageActionView(session, item_id, option_key=option_key, index=active))
                return
            await open_action_editor(
                interaction,
                language,
                config,
                inherited,
                action_type,
                active,
                after_for(active),
                library=session.library,
                open_form=open_form,
                in_form=draft.is_form,
            )

        async def on_delete(interaction: Interaction) -> None:
            """Delete the selected action."""
            assert active is not None
            del actions[active]
            session.library.prune_forms()
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=active))

        async def on_up(interaction: Interaction) -> None:
            """Move the selected action one position up."""
            assert active is not None and active > 0
            actions[active - 1], actions[active] = actions[active], actions[active - 1]
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=active - 1))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected action one position down."""
            assert active is not None and active < len(actions) - 1
            actions[active + 1], actions[active] = actions[active], actions[active + 1]
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=active + 1))

        # Deleting the message has nothing to change in it, so there is nothing to edit either.
        editable = active is not None and actions[active].type is not ActionType.DELETE_MESSAGE
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(
            nav_row,
            on_edit,
            label=screen(language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            disabled=not editable,
        )
        add_button(
            nav_row,
            on_delete,
            label=screen(language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=active is None,
        )
        if len(actions) > 1:  # moving an action needs another one to move past
            add_button(
                nav_row,
                on_up,
                label=ts(language, "buttons.up"),
                style=ButtonStyle.blurple,
                emoji="⬆️",
                disabled=active is None or active <= 0,
            )
            add_button(
                nav_row,
                on_down,
                label=ts(language, "buttons.down"),
                style=ButtonStyle.blurple,
                emoji="⬇️",
                disabled=active is None or active >= len(actions) - 1,
            )
        self.add_item(nav_row)

        switch_row: ActionRow = ActionRow()
        switch_options = [
            SelectOption(
                label=f"{number + 1}. {action_name(language, action.type, len(action.roles))}"[:100],
                value=str(number),
                default=number == active,
            )
            for number, action in enumerate(actions)
        ]

        async def on_switch(interaction: Interaction) -> None:
            """Select another action."""
            if not actions:
                return
            view = ItemActionsView(session, item_id, option_key=option_key, active_index=int(switch_select.values[0]))
            await show(interaction, view)

        switch_select = add_select(
            switch_row,
            on_switch,
            options=switch_options,
            placeholder=screen(language, "placeholders.switch_action" if actions else "placeholders.no_actions"),
            disabled=not actions,
        )
        self.add_item(switch_row)

        add_row: ActionRow = ActionRow()
        full = len(actions) >= MAX_ACTIONS_PER_ITEM

        async def on_add(interaction: Interaction) -> None:
            """Start adding the chosen kind of action: roles and messages have a screen of their own."""
            group = add_select_item.values[0]
            if group in ("roles", "message"):
                problem = adding_problem(language, config, group)
                if problem is not None:
                    await after_for(active)(interaction, problem)
                    return
                screen = RoleActionView if group == "roles" else MessageActionView
                await show(interaction, screen(session, item_id, option_key=option_key))
                return

            action_type = ActionType(group)
            await open_action_editor(
                interaction,
                language,
                config,
                inherited,
                action_type,
                None,
                after_for(len(actions)),
                library=session.library,
                open_form=open_form,
                in_form=draft.is_form,
            )

        add_select_item = add_select(
            add_row,
            on_add,
            options=action_group_options(language, exclude={"open_form"} if draft.is_form else ()),
            placeholder=screen(language, "placeholders.add_action_full" if full else "placeholders.add_action"),
            disabled=full,
        )
        self.add_item(add_row)

        if error:
            self.add_error(error)


class RoleActionView(BuilderLayoutView):
    """The screen of a role action: what it does to the roles (add, remove, toggle, set) and which roles. The
    controls change a working copy; "save" checks the action as a whole and stores it."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown the action belongs to. `index` is the
        position of the action to change (`None` for a new one) and `action` the working copy so far."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        if action is None:
            action = config.actions[index] if index is not None else Action(ActionType.ROLE_ADD)
        working = action

        title, description = screen_texts(language, working)
        self.add_item(sections_container(f"### {title}\n{description}", role_sections(language, working)))

        def again(updated: Action, problem: str | None = None) -> RoleActionView:
            """This screen once more, with `updated` as the working copy."""
            return RoleActionView(session, item_id, option_key=option_key, index=index, action=updated, error=problem)

        async def on_back(interaction: Interaction) -> None:
            """Leave without saving."""
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=index))

        async def on_save(interaction: Interaction) -> None:
            """Store the action - or say what is wrong with it."""
            problem = save_action(language, config, inherited, index, working, in_form=draft.is_form)
            if problem is not None:
                await show(interaction, again(working, problem))
                return
            position = index if index is not None else len(config.actions) - 1
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=position))

        async def on_type(interaction: Interaction) -> None:
            """Turn the action into another type - unless it would contradict the other actions."""
            changed = with_type(working, ActionType(type_select.values[0]))
            problem = clash_problem(language, config, index, changed, inherited)
            await show(interaction, again(working if problem else changed, problem))

        async def on_roles(interaction: Interaction) -> None:
            """The roles of the action were picked - if this user may hand them out."""
            guild, member = interaction.guild, interaction.user
            assert guild is not None and isinstance(member, Member)
            roles = [role for role in roles_select.values if isinstance(role, Role)]
            problem = chosen_role_problem(language, roles, member, guild)
            if problem is not None:
                await show(interaction, again(working, problem))
                return
            chosen = with_roles(working, [role.id for role in roles])
            problem = clash_problem(language, config, index, chosen, inherited)
            await show(interaction, again(working if problem else chosen, problem))

        nav_row: ActionRow = ActionRow()
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(nav_row, on_save, label=shared_t(language, "action_screen.save"), style=ButtonStyle.green, emoji="💾")
        self.add_item(nav_row)

        type_row: ActionRow = ActionRow()
        type_select = add_select(
            type_row,
            on_type,
            options=type_options(language, ROLE_TYPES, working.type, len(working.roles)),
            placeholder=shared_t(language, "action_screen.type_placeholder"),
        )
        self.add_item(type_row)

        roles_row: ActionRow = ActionRow()
        roles_select = role_select(language, working)
        roles_select.callback = on_roles  # type: ignore[method-assign]
        roles_row.add_item(roles_select)
        self.add_item(roles_row)

        if error:
            self.add_error(error)


class MessageActionView(BuilderLayoutView):
    """The screen of a message action: how the message reaches people (reply, direct message, channel message), what it
    says and - for a channel message - where it goes. The controls change a working copy; "save" checks the action
    as a whole and stores it."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown the action belongs to. `index` is the
        position of the action to change (`None` for a new one) and `action` the working copy so far."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        if action is None:
            action = config.actions[index] if index is not None else new_message_action(language, config)
        working = action

        title, description = screen_texts(language, working)
        questions = [question.label for question in draft.questions] if draft.is_form else []
        preview = message_preview(language, session.slashcmd_author, session.slashcmd_channel, questions)
        variables = variables_help(language, in_form=draft.is_form)
        self.add_item(
            sections_container(
                f"### {title}\n{description}\n\n{variables}", message_sections(language, working, preview=preview)
            )
        )

        def again(updated: Action, problem: str | None = None) -> MessageActionView:
            """This screen once more, with `updated` as the working copy."""
            return MessageActionView(session, item_id, option_key=option_key, index=index, action=updated, error=problem)

        async def on_back(interaction: Interaction) -> None:
            """Leave without saving."""
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=index))

        async def on_save(interaction: Interaction) -> None:
            """Store the action - or say what is wrong with it."""
            problem = save_action(language, config, inherited, index, working, in_form=draft.is_form)
            if problem is not None:
                await show(interaction, again(working, problem))
                return
            position = index if index is not None else len(config.actions) - 1
            await show(interaction, ItemActionsView(session, item_id, option_key=option_key, active_index=position))

        async def on_type(interaction: Interaction) -> None:
            """Turn the action into another type - unless it would contradict the other actions."""
            changed = with_type(working, ActionType(type_select.values[0]))
            problem = clash_problem(language, config, index, changed, inherited)
            await show(interaction, again(working if problem else changed, problem))

        async def after_content(interaction: Interaction, payload: MessagePayload | None, problem: str | None) -> None:
            """Take the message over once its modal is done."""
            if problem is not None or payload is None:
                await show(interaction, again(working, problem))
                return
            await show(interaction, again(with_payload(working, payload)))

        async def on_content(interaction: Interaction) -> None:
            """Open the modal to write the message."""
            templates = await load_template_choices(interaction.user.id)
            await interaction.response.send_modal(MessageContentModal(language, working.payload, templates, after_content))

        async def on_channel(interaction: Interaction) -> None:
            """The channel of a channel message was picked - if this user may write there."""
            assert channel_select_item is not None
            member = interaction.user
            assert isinstance(member, Member)
            channel = await resolve_selected_channel(channel_select_item.values[0])
            if not can_post_in(channel, member):
                problem = shared_t(language, "errors.channel_no_access", channel=channel.mention)
                await show(interaction, again(working, problem))
                return
            await show(interaction, again(with_channel(working, channel.id)))

        nav_row: ActionRow = ActionRow()
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(
            nav_row,
            on_content,
            label=shared_t(language, "action_screen.message.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
        )
        add_button(nav_row, on_save, label=shared_t(language, "action_screen.save"), style=ButtonStyle.green, emoji="💾")
        self.add_item(nav_row)

        type_row: ActionRow = ActionRow()
        type_select = add_select(
            type_row,
            on_type,
            options=type_options(language, MESSAGE_TYPES, working.type),
            placeholder=shared_t(language, "action_screen.type_placeholder"),
        )
        self.add_item(type_row)

        channel_select_item: ChannelSelect | None = None
        if working.type is ActionType.SEND_CHANNEL:
            channel_row: ActionRow = ActionRow()
            channel_select_item = channel_select(language, working)
            channel_select_item.callback = on_channel  # type: ignore[method-assign]
            channel_row.add_item(channel_select_item)
            self.add_item(channel_row)

        if error:
            self.add_error(error)


class ItemConditionsView(BuilderLayoutView):
    """Lists the restrictions of one item (a dropdown option, or the dropdown as a whole) and lets the user add,
    change and delete them."""

    def __init__(
        self,
        session: ContainerBuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown whose restrictions these are (or `None` for
        a button or the dropdown as a whole). `active_index` is the selected restriction and `error` an optional
        error box to show."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        conditions = config.conditions
        active = _clamp(active_index, len(conditions))

        option = draft.option(option_key) if option_key is not None else None
        title = screen(language, "conditions.title_option", name=option_name(option)) if option is not None else None
        header = f"### {title or screen(language, 'conditions.title')}"
        lines = [screen(language, "conditions.description")]
        if conditions:
            lines += ["", f"**{screen(language, 'conditions.list')}:**"]
        for number, condition in enumerate(conditions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {describe_condition(language, condition)}")
        self.add_item(info_container(header + "\n" + "\n".join(lines)))

        def after_for(index: int | None) -> AfterEdit:
            """The callback that shows this screen again once a modal is done, with `index` selected."""

            async def after(interaction: Interaction, problem: str | None) -> None:
                """Show this screen again once a modal is done, with `index` selected."""
                view = ItemConditionsView(session, item_id, option_key=option_key, active_index=index, error=problem)
                await show(interaction, view)

            return after

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the form, the option list, or the item list."""
            if draft.is_form:
                await show(interaction, FormView(session, item_id))
                return
            if option_key is not None:
                await show(interaction, OptionsView(session, item_id, active_key=option_key))
                return
            await show(interaction, InteractiveHubView(session))

        async def on_edit(interaction: Interaction) -> None:
            """Open the modal to change the selected restriction."""
            assert active is not None
            condition_type = conditions[active].type
            await open_condition_editor(
                interaction,
                language,
                config,
                inherited,
                condition_type,
                active,
                after_for(active),
                below=dependent_configs(draft, option_key),
            )

        async def on_delete(interaction: Interaction) -> None:
            """Delete the selected restriction - unless the item needs it."""
            assert active is not None
            problem = delete_condition(language, config, inherited, active)
            view = ItemConditionsView(session, item_id, option_key=option_key, active_index=active, error=problem)
            await show(interaction, view)

        # "Once per person" has nothing to configure, so there is nothing to edit either.
        editable = active is not None and conditions[active].type is not ConditionType.ONCE_PER_USER
        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(
            nav_row,
            on_edit,
            label=screen(language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            disabled=not editable,
        )
        add_button(
            nav_row,
            on_delete,
            label=screen(language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=active is None,
        )
        self.add_item(nav_row)

        switch_row: ActionRow = ActionRow()
        switch_options = [
            SelectOption(
                label=shared_t(language, f"editor.condition_name.{condition.type.value}")[:100],
                value=str(number),
                default=number == active,
            )
            for number, condition in enumerate(conditions)
        ]

        async def on_switch(interaction: Interaction) -> None:
            """Select another restriction."""
            if not conditions:
                return
            view = ItemConditionsView(session, item_id, option_key=option_key, active_index=int(switch_select.values[0]))
            await show(interaction, view)

        switch_select = add_select(
            switch_row,
            on_switch,
            options=switch_options,
            placeholder=screen(language, "placeholders.switch_condition" if conditions else "placeholders.no_conditions"),
            disabled=not conditions,
        )
        self.add_item(switch_row)

        add_row: ActionRow = ActionRow()
        add_options = condition_type_options(language, {condition.type for condition in conditions})
        limit_reached = len(conditions) >= MAX_CONDITIONS_PER_ITEM
        add_placeholder = (
            "placeholders.add_condition_limit"
            if limit_reached
            else "placeholders.add_condition"
            if add_options
            else "placeholders.add_condition_full"
        )

        async def on_add(interaction: Interaction) -> None:
            """Start adding the chosen restriction."""
            condition_type = ConditionType(add_select_item.values[0])
            await open_condition_editor(
                interaction,
                language,
                config,
                inherited,
                condition_type,
                None,
                after_for(len(conditions)),
                below=dependent_configs(draft, option_key),
            )

        add_select_item = add_select(
            add_row,
            on_add,
            options=add_options,
            placeholder=screen(language, add_placeholder),
            disabled=limit_reached or not add_options,
        )
        self.add_item(add_row)

        if error:
            self.add_error(error)


class QuestionsView(BuilderLayoutView):
    """Lists the questions of one form and lets the user add, change, delete and reorder them."""

    def __init__(
        self, session: ContainerBuilderSession, item_id: int, *, active_index: int | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the form, `active_index` the selected question and `error` an optional error box to show."""
        super().__init__()
        self.session = session
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        questions = draft.questions
        active = _clamp(active_index, len(questions))

        header = f"### {screen(language, 'questions.title', name=draft_name(language, draft))}"
        lines = [screen(language, "questions.description")]
        if questions:
            lines += ["", f"**{screen(language, 'questions.list')}:**"]
        for number, question in enumerate(questions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {describe_question(language, number + 1, question)}")
        self.add_item(info_container(header + "\n" + "\n".join(lines)))

        def after_question() -> AfterQuestion:
            """Build the callback that returns to this list after a question was added or changed."""

            async def after(interaction: Interaction, index: int | None, problem: str | None) -> None:
                """Show the question list again with the changed question selected."""
                await show(interaction, QuestionsView(session, item_id, active_index=index, error=problem))

            return after

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the form."""
            await show(interaction, FormView(session, item_id))

        async def on_add(interaction: Interaction) -> None:
            """Open the modal to add a question."""
            await interaction.response.send_modal(QuestionModal(language, draft, None, after_question()))

        async def on_edit(interaction: Interaction) -> None:
            """Open the modal to change the selected question."""
            assert active is not None
            await interaction.response.send_modal(QuestionModal(language, draft, active, after_question()))

        async def on_delete(interaction: Interaction) -> None:
            """Delete the selected question."""
            assert active is not None
            del questions[active]
            await show(interaction, QuestionsView(session, item_id, active_index=active))

        add_button(nav_row, on_back, label=ts(language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")
        add_button(
            nav_row,
            on_add,
            label=screen(language, "buttons.question_add"),
            style=ButtonStyle.green,
            emoji="➕",
            disabled=len(questions) >= MAX_QUESTIONS_PER_FORM,
        )
        add_button(
            nav_row,
            on_edit,
            label=screen(language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            disabled=active is None,
        )
        add_button(
            nav_row,
            on_delete,
            label=screen(language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            disabled=active is None,
        )
        self.add_item(nav_row)

        order_row: ActionRow = ActionRow()

        async def on_up(interaction: Interaction) -> None:
            """Move the selected question one position up."""
            assert active is not None and active > 0
            questions[active - 1], questions[active] = questions[active], questions[active - 1]
            await show(interaction, QuestionsView(session, item_id, active_index=active - 1))

        async def on_down(interaction: Interaction) -> None:
            """Move the selected question one position down."""
            assert active is not None and active < len(questions) - 1
            questions[active + 1], questions[active] = questions[active], questions[active + 1]
            await show(interaction, QuestionsView(session, item_id, active_index=active + 1))

        add_button(
            order_row,
            on_up,
            label=ts(language, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            disabled=active is None or active <= 0,
        )
        add_button(
            order_row,
            on_down,
            label=ts(language, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            disabled=active is None or active >= len(questions) - 1,
        )
        self.add_item(order_row)

        switch_row: ActionRow = ActionRow()
        switch_options = [
            SelectOption(label=f"{number + 1}. {question.label}"[:100], value=str(number), default=number == active)
            for number, question in enumerate(questions)
        ]

        async def on_switch(interaction: Interaction) -> None:
            """Select another question."""
            if not questions:
                return
            await show(interaction, QuestionsView(session, item_id, active_index=int(switch_select.values[0])))

        switch_select = add_select(
            switch_row,
            on_switch,
            options=switch_options,
            placeholder=screen(language, "placeholders.switch_question" if questions else "placeholders.no_questions"),
            disabled=not questions,
        )
        self.add_item(switch_row)

        if error:
            self.add_error(error)
