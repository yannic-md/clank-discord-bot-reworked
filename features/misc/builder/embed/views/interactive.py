from collections.abc import Awaitable, Callable
from typing import Any

from discord import ButtonStyle, Colour, Embed, Interaction, Member, Role, SelectOption
from discord.ui import Button, ChannelSelect, RoleSelect, Select

from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.channels import can_post_in, resolve_selected_channel
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.placement import (
    NEW_ROW_VALUE,
    PREVIEW_ROWS,
    delete_item,
    describe_layout,
    describe_placement,
    move_in_row,
    place_item,
    placement_options,
    preview_rows,
    row_of,
)
from features.misc.builder.embed.views.base import BuilderScreenView, show
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
    BLANK_LINE,
    BULLET,
    BULLET_ACTIVE,
    action_group_options,
    action_name,
    condition_type_options,
    describe_action,
    describe_condition,
    describe_option,
    describe_question,
    draft_name,
    draft_sections,
    section_fields,
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
    placement_text,
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

_PREFIX = "embed:interactive"


def _t(session: BuilderSession, key: str, **variables: Any) -> str:
    """Translate a key of the `builder.embed` locale domain."""
    return translate(session.language, f"builder.embed.{key}", **variables)


def _ts(session: BuilderSession, key: str, **variables: Any) -> str:
    """Translate a key both builders share."""
    return translate(session.language, f"builder.{key}", **variables)


def _clamp(index: int | None, length: int) -> int | None:
    """`index` limited to the valid positions of a list with `length` entries (`None` for an empty list)."""
    if length == 0:
        return None
    return min(max(index or 0, 0), length - 1)


def _action_label(language: SupportedLanguage, number: int, action: Action) -> str:
    """ "1. Add roles": an action as it is listed in a dropdown."""
    return f"{number + 1}. {action_name(language, action.type, len(action.roles))}"[:100]


def _after_button(session: BuilderSession) -> AfterButton:
    """What happens once a button modal is done: show the item list with that item selected."""

    async def after(interaction: Interaction, item_id: int | None, error: str | None) -> None:
        """Show the screen that follows a finished modal."""
        if item_id is not None:
            session.active_item_id = item_id
        await show(interaction, InteractiveHubView(session, error=error))

    return after


def _after_create(session: BuilderSession) -> AfterButton:
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


class _InteractiveScreen(BuilderScreenView):
    """Shared plumbing of the button screens: one info embed and controls added in code instead of decorators."""

    def __init__(self, session: BuilderSession) -> None:
        """Create an empty screen; subclasses fill `info_embed` and add their controls."""
        super().__init__()
        self.session = session
        self.info_embed: Embed = Embed(colour=Colour.blurple())
        self.content = None
        self.embeds = [self.info_embed]

    def add_button(
        self, name: str, callback: Any, *, label: str, style: ButtonStyle, emoji: str, row: int, disabled: bool = False
    ) -> Button:
        """Add a button to the screen. Its `custom_id` carries the `embed:` prefix so that a click after a restart
        leaves the preview alone (see the dead-interaction handling)."""
        item: Button = Button(
            label=label,
            style=style,
            emoji=emoji,
            row=row,
            disabled=disabled,
            custom_id=f"{_PREFIX}:{type(self).__name__}:{name}",
        )
        item.callback = callback  # type: ignore[method-assign]
        self.add_item(item)
        return item

    def add_select(
        self, name: str, callback: Any, *, options: list[SelectOption], placeholder: str, row: int, disabled: bool = False
    ) -> Select:
        """Add a dropdown to the screen (an empty option list gets a "—" placeholder entry)."""
        item: Select = Select(
            options=options or [SelectOption(label="—", value="__none__")],
            placeholder=placeholder,
            row=row,
            disabled=disabled,
            custom_id=f"{_PREFIX}:{type(self).__name__}:{name}",
        )
        item.callback = callback  # type: ignore[method-assign]
        self.add_item(item)
        return item

    def add_component(self, name: str, item: RoleSelect | ChannelSelect, callback: Any, *, row: int) -> None:
        """Add a role or channel picker to the screen, as `add_select` does for a dropdown of texts."""
        item.row = row
        item.custom_id = f"{_PREFIX}:{type(self).__name__}:{name}"
        item.callback = callback  # type: ignore[method-assign]
        self.add_item(item)

    def set_error(self, error: str | None) -> None:
        """Show `error` as one more (red) embed below the info embed, if the screen has room for it."""
        if error:
            self.embeds = [*self.embeds, Embed(description=error, colour=Colour.red())]


async def _create_element(session: BuilderSession, interaction: Interaction, kind: str) -> None:
    """Start creating a clickable element: the modal for how it looks opens (see `start_element`)."""
    await start_element(interaction, session.language, session.library, kind, _after_create(session))


class InteractiveHubView(_InteractiveScreen):
    """The "Buttons & Dropdowns" screen: a dropdown with the clickable elements and a button to create more. While
    nothing is selected it explains what the screen is for; with an element selected it shows just that element."""

    def __init__(self, session: BuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error text to show."""
        super().__init__(session)
        language = session.language
        library = session.library

        active = library.get(session.active_item_id) if session.active_item_id is not None else None
        if active is not None and active.is_form:  # a form is changed through the action that opens it
            active = None
        session.active_item_id = active.id if active else None

        if active is None:
            self.info_embed.title = hub_title(language)
            self.info_embed.description = overview_text(language, webhook=session.webhook.enabled)
            if session.webhook.enabled:
                self.info_embed.colour = Colour.orange()
        else:
            placement = describe_placement(session, active.id)
            self.info_embed.title = item_title(language, active)
            # the blank line below the text keeps the fields from starting right under it
            self.info_embed.description = f"{item_description(language, active, preview=True)}\n{BLANK_LINE * 2}"
            sections = draft_sections(language, active, placement=placement, library=library)
            for name, value, inline in section_fields(sections):
                self.info_embed.add_field(name=name, value=value, inline=inline)

        self._add_navigation(active)
        if active is not None:
            self._add_edit_row(active)
        if library.elements():
            self._add_element_select(active)
        if active is not None:
            self._add_place_button(active)
        self.set_error(error)

    def _add_navigation(self, active: ItemDraft | None) -> None:
        """The first row. Without a selection: back to the main screen and add an element. With one: back to the
        overview, delete that element and - if there are several - move it up or down."""
        from features.misc.builder.embed.views.gui import EmbedBuilderGUI

        session = self.session
        language = session.language
        library = session.library

        async def on_back(interaction: Interaction) -> None:
            """Go back: from a selected element to the overview, from the overview to the main screen."""
            if active is None:
                await show(interaction, EmbedBuilderGUI(session))
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
            following = element_after(library, active.id, self._placed)
            delete_item(session, active.id)
            session.active_item_id = following
            await show(interaction, InteractiveHubView(session))

        def mover(offset: int) -> Any:
            """The callback that moves the selected element by `offset` places in its list."""

            async def on_move(interaction: Interaction) -> None:
                """Move the selected element among those in the same state and show the screen again."""
                assert active is not None
                group = order_group(library, active, self._placed)
                target = [draft.id for draft in group].index(active.id) + offset
                if 0 <= target < len(group):
                    library.swap(active.id, group[target].id)
                await show(interaction, InteractiveHubView(session))

            return on_move

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        if active is None:
            self.add_button(
                "create",
                on_create,
                label=hub_text(language, "create_button"),
                style=ButtonStyle.green,
                emoji="➕",
                row=0,
                disabled=library.is_full,
            )
            return

        if active.is_link:  # a link button has no actions or conditions, so its look has the first row to itself
            self.add_button(
                "look",
                self._look_callback(active),
                label=screen(session.language, "buttons.look"),
                style=ButtonStyle.blurple,
                emoji="✏️",
                row=0,
            )
        self.add_button(
            "delete",
            on_delete,
            label=delete_label(language, active),
            style=ButtonStyle.red,
            emoji="🗑️",
            row=0,
        )
        group = order_group(library, active, self._placed)
        if len(group) < 2:
            return

        position = [draft.id for draft in group].index(active.id)
        self.add_button(
            "up",
            mover(-1),
            label=_ts(session, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            row=0,
            disabled=position == 0,
        )
        self.add_button(
            "down",
            mover(1),
            label=_ts(session, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            row=0,
            disabled=position == len(group) - 1,
        )

    def _placed(self, item_id: int) -> bool:
        """Whether the element sits in the message."""
        return bool(describe_placement(self.session, item_id))

    def _add_element_select(self, active: ItemDraft | None) -> None:
        """The dropdown of the clickable elements - there is none while no element exists."""
        session = self.session
        language = session.language
        options = element_options(
            language,
            session.library,
            active_id=active.id if active is not None else None,
            is_placed=self._placed,
            place_of=lambda item_id: describe_placement(session, item_id),
        )

        async def on_select(interaction: Interaction) -> None:
            """Select an element to see and change it."""
            session.active_item_id = int(element_select.values[0])
            await show(interaction, InteractiveHubView(session))

        element_select = self.add_select(
            "elements",
            on_select,
            options=options,
            placeholder=hub_text(language, "elements.placeholder"),
            row=2,
        )

    def _add_place_button(self, active: ItemDraft) -> None:
        """The button to place the selected element in the message. It sits below the dropdown, as it is the step
        that matters most, with the preview of the element - always disabled - to its left. A dropdown has no preview:
        a second dropdown on the screen would only be confusing, and it is listed with its options anyway."""
        session = self.session

        async def on_place(interaction: Interaction) -> None:
            """Open the screen to place the element in the message."""
            await show(interaction, PlacementView(session, active.id))

        if not active.is_select:
            preview = preview_component(active)
            if isinstance(preview, Button) and not active.is_link:  # a link button has no `custom_id`
                preview.custom_id = f"{_PREFIX}:{type(self).__name__}:preview"  # the others carry ours (see `add_button`)
            preview.row = 3
            self.add_item(preview)

        self.add_button(
            "place", on_place, label=screen(session.language, "buttons.place"), style=ButtonStyle.green, emoji="📍", row=3
        )

    def _look_callback(self, active: ItemDraft) -> Any:
        """The callback that opens the modal to change how the element looks (a dropdown: placeholder and limits)."""
        session = self.session
        language = session.language
        library = session.library

        async def on_look(interaction: Interaction) -> None:
            """Open the modal to change how the element looks."""
            if active.is_select:
                await interaction.response.send_modal(SelectLookModal(language, active, _after_button(session)))
                return
            await interaction.response.send_modal(
                ButtonModal(language, library, active.kind, active, _after_button(session))
            )

        return on_look

    def _add_edit_row(self, active: ItemDraft) -> None:
        """The row with what can be done to the selected element: change its look, set its actions or options and
        restrict it. A link button has neither, so it has no such row: its look sits in the first row."""
        session = self.session
        if active.is_link:
            return

        async def on_inner(interaction: Interaction) -> None:
            """Open the list of the button's actions - or of the dropdown's options."""
            if active.is_select:
                await show(interaction, OptionsView(session, active.id))
                return
            await show(interaction, ItemActionsView(session, active.id))

        async def on_conditions(interaction: Interaction) -> None:
            """Open the list of the element's restrictions."""
            await show(interaction, ItemConditionsView(session, active.id))

        self.add_button(
            "look",
            self._look_callback(active),
            label=screen(session.language, "buttons.look"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=1,
        )
        self.add_button(
            "inner",
            on_inner,
            label=screen(session.language, "buttons.options" if active.is_select else "buttons.actions"),
            style=ButtonStyle.gray,
            emoji="🧩" if active.is_select else "⚙️",
            row=1,
        )
        self.add_button(
            "conditions",
            on_conditions,
            label=screen(session.language, "buttons.conditions"),
            style=ButtonStyle.gray,
            emoji="🔒",
            row=1,
        )


class ElementKindView(_InteractiveScreen):
    """Asks which kind of clickable element to create: a link button, a button or a dropdown. With a custom sender
    only link buttons are on offer, and the screen says so."""

    def __init__(self, session: BuilderSession, *, error: str | None = None) -> None:
        """Build the explanation and the dropdown of kinds; `error` is an optional error text to show."""
        super().__init__(session)
        language = session.language
        webhook = session.webhook.enabled

        self.info_embed.title = hub_text(language, "kind_view.title")
        self.info_embed.description = kind_view_text(language, webhook=webhook)
        if webhook:
            self.info_embed.colour = Colour.orange()

        async def on_back(interaction: Interaction) -> None:
            """Go back to the overview."""
            await show(interaction, InteractiveHubView(session))

        async def on_select(interaction: Interaction) -> None:
            """Create an element of the chosen kind."""
            await _create_element(session, interaction, kind_select.values[0])

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        kind_select = self.add_select(
            "kind",
            on_select,
            options=kind_options(language, element_kinds(webhook=webhook)),
            placeholder=hub_text(language, "kind_view.placeholder"),
            row=1,
        )
        self.set_error(error)


class FormView(_InteractiveScreen):
    """Everything about one form: its title, its questions, what happens once it is submitted and who may use it.
    A form belongs to the action of a button (or dropdown option) that opens it."""

    def __init__(self, session: BuilderSession, form_id: int, *, error: str | None = None) -> None:
        """`form_id` is the form and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language
        library = session.library

        form = library.get(form_id)
        assert form is not None and form.is_form
        self.info_embed.title = form_title(language)
        self.info_embed.description = f"{form_description(language, form)}\n{BLANK_LINE}"
        for name, value, inline in section_fields(draft_sections(language, form, placement=None, library=library)):
            self.info_embed.add_field(name=name, value=value, inline=inline)

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

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "title",
            on_title,
            label=screen(session.language, "buttons.form_title"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=0,
        )
        self.add_button(
            "questions",
            on_questions,
            label=screen(session.language, "buttons.questions"),
            style=ButtonStyle.gray,
            emoji="❓",
            row=0,
        )
        self.add_button(
            "actions",
            on_actions,
            label=screen(session.language, "buttons.actions"),
            style=ButtonStyle.gray,
            emoji="⚙️",
            row=1,
        )
        self.add_button(
            "conditions",
            on_conditions,
            label=screen(session.language, "buttons.conditions"),
            style=ButtonStyle.gray,
            emoji="🔒",
            row=1,
        )
        self.set_error(error)


class PlacementView(_InteractiveScreen):
    """Lets the user choose where an item goes: a new row or a row with room left. The screen stays open while the
    item is moved around, and shows the items that are placed. While nothing is placed yet there is nothing to choose
    from, so the user is only asked whether to place the item at all."""

    def __init__(self, session: BuilderSession, item_id: int, *, error: str | None = None) -> None:
        """`item_id` is the item to place and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None

        self.info_embed.title = screen(session.language, "placement.title", name=element_name(language, draft))

        async def on_place(interaction: Interaction, target: str) -> None:
            """Put the item in the chosen place, or take it out of the message again - and show the result."""
            await show(interaction, PlacementView(session, item_id, error=place_item(session, draft, target)))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the item list."""
            await show(interaction, InteractiveHubView(session))

        if not session.button_rows:
            self.info_embed.description = screen(session.language, "placement.confirm")

            async def on_yes(interaction: Interaction) -> None:
                """Place the item in a row of its own."""
                await on_place(interaction, NEW_ROW_VALUE)

            self.add_button("yes", on_yes, label=_ts(session, "buttons.yes"), style=ButtonStyle.green, emoji="✅", row=0)
            self.add_button("no", on_back, label=_ts(session, "buttons.no"), style=ButtonStyle.red, emoji="🛑", row=0)
            self.set_error(error)
            return

        rows = preview_rows(session)
        # a message has five rows; the screen has room to preview fewer of them
        self.info_embed.description = placement_text(
            language,
            _t(session, "info.placement.rows"),
            describe_layout(session),
            shown=PREVIEW_ROWS,
            total=len(rows),
        )

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)

        # Two buttons in a row can swap places: the item moves along its row, one place at a time.
        neighbours = row_of(session, item_id)
        if len(neighbours) > 1:

            def mover(offset: int) -> Callable[[Interaction], Awaitable[None]]:
                """The callback that moves the item `offset` places along its row and shows the screen again."""

                async def move(interaction: Interaction) -> None:
                    """Move the item along its row."""
                    move_in_row(session, item_id, offset)
                    await show(interaction, PlacementView(session, item_id))

                return move

            position = neighbours.index(item_id)
            self.add_button(
                "left",
                mover(-1),
                label=_ts(session, "buttons.left"),
                style=ButtonStyle.blurple,
                emoji="⬅️",
                row=0,
                disabled=position == 0,
            )
            self.add_button(
                "right",
                mover(1),
                label=_ts(session, "buttons.right"),
                style=ButtonStyle.blurple,
                emoji="➡️",
                row=0,
                disabled=position == len(neighbours) - 1,
            )

        options = placement_options(session, draft)

        async def on_select(interaction: Interaction) -> None:
            """Put the item in the chosen place."""
            value = target_select.values[0]
            if value == "__none__":
                return
            await on_place(interaction, value)

        target_select = self.add_select(
            "target",
            on_select,
            options=options,
            placeholder=screen(
                session.language, "placeholders.placement_target" if options else "placeholders.placement_empty"
            ),
            row=1,
            disabled=not options,
        )

        # The placed items as the message shows them, below the dropdown - disabled, as it is only a preview.
        for offset, row in enumerate(rows[:PREVIEW_ROWS]):
            for placed in row:
                preview = preview_component(placed)
                if isinstance(preview, Button | Select) and not placed.is_link:  # a link button has no `custom_id`
                    preview.custom_id = f"{_PREFIX}:{type(self).__name__}:preview:{placed.id}"  # the others carry ours
                preview.row = 2 + offset
                self.add_item(preview)
        self.set_error(error)


class OptionsView(_InteractiveScreen):
    """Lists the options of one dropdown and lets the user add, restyle, delete and reorder them - and, in a
    dropdown of texts, open the actions and restrictions of the selected one."""

    def __init__(
        self, session: BuilderSession, item_id: int, *, active_key: str | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the dropdown, `active_key` the selected option and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        options = draft.options
        active = draft.option(active_key) if active_key is not None else None
        if active is None and options:
            active = options[0]
        roles_mode = draft.mode is SelectMode.ROLES

        lines = [screen(session.language, "options.description." + draft.mode.value)]
        if options:
            lines += ["", f"**{screen(session.language, 'options.list')}:**"]
        for number, option in enumerate(options, 1):
            marker = BULLET_ACTIVE if option is active else BULLET
            lines.append(f"{marker} {number}. {describe_option(language, draft, option)}")
        self.info_embed.title = screen(session.language, "options.title")
        self.info_embed.description = "\n".join(lines)

        def after_option() -> AfterOption:
            """The callback that shows the option list again once a modal is done."""

            async def after(interaction: Interaction, key: str | None, problem: str | None) -> None:
                """Show the option list again with the changed option selected."""
                await show(interaction, OptionsView(session, item_id, active_key=key or active_key, error=problem))

            return after

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
        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        if len(options) < 25:
            self.add_button(
                "add",
                on_add,
                label=screen(session.language, "buttons.option_add"),
                style=ButtonStyle.green,
                emoji="➕",
                row=0,
            )
        if active is not None:
            self.add_button(
                "delete",
                on_delete,
                label=screen(session.language, "buttons.delete"),
                style=ButtonStyle.red,
                emoji="🗑️",
                row=0,
            )

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
            self.add_button(
                "look", on_look, label=screen(session.language, "buttons.look"), style=ButtonStyle.blurple, emoji="✏️", row=1
            )
        if active is not None and not roles_mode:  # the options of a role dropdown have no actions or restrictions
            self.add_button(
                "actions",
                on_actions,
                label=screen(session.language, "buttons.actions"),
                style=ButtonStyle.gray,
                emoji="⚙️",
                row=1,
            )
            self.add_button(
                "conditions",
                on_conditions,
                label=screen(session.language, "buttons.conditions"),
                style=ButtonStyle.gray,
                emoji="🔒",
                row=1,
            )
        if position is not None and position > 0:
            self.add_button("up", on_up, label=_ts(session, "buttons.up"), style=ButtonStyle.blurple, emoji="⬆️", row=1)
        if position is not None and position < len(options) - 1:
            self.add_button("down", on_down, label=_ts(session, "buttons.down"), style=ButtonStyle.blurple, emoji="⬇️", row=1)

        async def on_switch(interaction: Interaction) -> None:
            """Select another option."""
            if not options:
                return
            await show(interaction, OptionsView(session, item_id, active_key=switch_select.values[0]))

        switch_select = self.add_select(
            "switch",
            on_switch,
            options=[
                SelectOption(
                    label=f"{number}. {option.label}"[:100],
                    value=option.key,
                    emoji=option.emoji,
                    description=option.description[:100] if option.description else None,
                    default=option is active,
                )
                for number, option in enumerate(options, 1)
            ],
            placeholder=screen(session.language, "placeholders.switch_option" if options else "placeholders.no_options"),
            row=2,
            disabled=not options,
        )
        self.set_error(error)


class ItemActionsView(_InteractiveScreen):
    """Lists the actions of one button (or dropdown option) and lets the user add, change, delete and reorder them."""

    def __init__(
        self,
        session: BuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown whose actions these are (or `None` for a
        button). `active_index` is the selected action and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        actions = config.actions
        active = _clamp(active_index, len(actions))

        description = "actions.description_form" if draft.is_form else "actions.description"
        lines = [screen(session.language, description)]
        if actions:
            lines += ["", f"**{screen(session.language, 'actions.list')}:**"]
        for number, action in enumerate(actions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {number + 1}. {describe_action(language, action, session.library)}")
        option = draft.option(option_key) if option_key is not None else None
        self.info_embed.title = (
            screen(session.language, "actions.title_option", name=option_name(option))
            if option is not None
            else screen(session.language, "actions.title")
        )
        self.info_embed.description = "\n".join(lines)

        def after_for(index: int | None) -> AfterEdit:
            """The callback that shows this screen again once a modal is done, with `index` selected."""

            async def after(interaction: Interaction, problem: str | None) -> None:
                """Show this screen again once a modal is done, with `index` selected."""
                view = ItemActionsView(session, item_id, option_key=option_key, active_index=index, error=problem)
                await show(interaction, view)

            return after

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
        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "edit",
            on_edit,
            label=screen(session.language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=0,
            disabled=not editable,
        )
        self.add_button(
            "delete",
            on_delete,
            label=screen(session.language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            row=0,
            disabled=active is None,
        )
        if len(actions) > 1:  # moving an action needs another one to move past
            self.add_button(
                "up",
                on_up,
                label=_ts(session, "buttons.up"),
                style=ButtonStyle.blurple,
                emoji="⬆️",
                row=0,
                disabled=active is None or active <= 0,
            )
            self.add_button(
                "down",
                on_down,
                label=_ts(session, "buttons.down"),
                style=ButtonStyle.blurple,
                emoji="⬇️",
                row=0,
                disabled=active is None or active >= len(actions) - 1,
            )

        async def on_switch(interaction: Interaction) -> None:
            """Select another action."""
            if not actions:
                return
            view = ItemActionsView(session, item_id, option_key=option_key, active_index=int(switch_select.values[0]))
            await show(interaction, view)

        switch_select = self.add_select(
            "switch",
            on_switch,
            options=[
                SelectOption(label=_action_label(language, number, action), value=str(number), default=number == active)
                for number, action in enumerate(actions)
            ],
            placeholder=screen(session.language, "placeholders.switch_action" if actions else "placeholders.no_actions"),
            row=1,
            disabled=not actions,
        )

        full = len(actions) >= MAX_ACTIONS_PER_ITEM

        async def on_add(interaction: Interaction) -> None:
            """Start adding the chosen kind of action: roles and messages have a screen of their own."""
            group = add_select.values[0]
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

        add_select = self.add_select(
            "add",
            on_add,
            options=action_group_options(language, exclude={"open_form"} if draft.is_form else ()),
            placeholder=screen(session.language, "placeholders.add_action_full" if full else "placeholders.add_action"),
            row=2,
            disabled=full,
        )
        self.set_error(error)


class RoleActionView(_InteractiveScreen):
    """The screen of a role action: what it does to the roles (add, remove, toggle, set) and which roles. The
    controls change a working copy; "save" checks the action as a whole and stores it."""

    def __init__(
        self,
        session: BuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown the action belongs to. `index` is the
        position of the action to change (`None` for a new one) and `action` the working copy so far."""
        super().__init__(session)
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
        self.info_embed.title = title
        self.info_embed.description = f"{description}\n{BLANK_LINE}"
        for name, value, inline in section_fields(role_sections(language, working)):
            self.info_embed.add_field(name=name, value=value, inline=inline)

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

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "save", on_save, label=shared_t(language, "action_screen.save"), style=ButtonStyle.green, emoji="💾", row=0
        )
        type_select = self.add_select(
            "type",
            on_type,
            options=type_options(language, ROLE_TYPES, working.type, len(working.roles)),
            placeholder=shared_t(language, "action_screen.type_placeholder"),
            row=1,
        )
        roles_select = role_select(language, working)
        self.add_component("roles", roles_select, on_roles, row=2)
        self.set_error(error)


class MessageActionView(_InteractiveScreen):
    """The screen of a message action: how the message reaches people (reply, direct message, channel message), what it
    says and - for a channel message - where it goes. The controls change a working copy; "save" checks the action
    as a whole and stores it."""

    def __init__(
        self,
        session: BuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown the action belongs to. `index` is the
        position of the action to change (`None` for a new one) and `action` the working copy so far."""
        super().__init__(session)
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
        self.info_embed.title = title
        self.info_embed.description = f"{description}\n\n{variables_help(language, in_form=draft.is_form)}\n{BLANK_LINE}"
        for name, value, inline in section_fields(message_sections(language, working, preview=preview)):
            self.info_embed.add_field(name=name, value=value, inline=inline)

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
                problem = translate(language, "builder.interactive.errors.channel_no_access", channel=channel.mention)
                await show(interaction, again(working, problem))
                return
            await show(interaction, again(with_channel(working, channel.id)))

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "content",
            on_content,
            label=shared_t(language, "action_screen.message.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=0,
        )
        self.add_button(
            "save", on_save, label=shared_t(language, "action_screen.save"), style=ButtonStyle.green, emoji="💾", row=0
        )
        type_select = self.add_select(
            "type",
            on_type,
            options=type_options(language, MESSAGE_TYPES, working.type),
            placeholder=shared_t(language, "action_screen.type_placeholder"),
            row=1,
        )
        channel_select_item: ChannelSelect | None = None
        if working.type is ActionType.SEND_CHANNEL:
            channel_select_item = channel_select(language, working)
            self.add_component("channel", channel_select_item, on_channel, row=2)
        self.set_error(error)


class ItemConditionsView(_InteractiveScreen):
    """Lists the restrictions of one item (a dropdown option, or the dropdown as a whole) and lets the user add,
    change and delete them."""

    def __init__(
        self,
        session: BuilderSession,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """`item_id` is the item and `option_key` the option of a dropdown whose restrictions these are (or `None` for
        a button or the dropdown as a whole). `active_index` is the selected restriction and `error` an optional
        error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        scope = scope_of(draft, option_key)
        assert scope is not None
        config, inherited = scope
        conditions = config.conditions
        active = _clamp(active_index, len(conditions))

        lines = [screen(session.language, "conditions.description")]
        if conditions:
            lines += ["", f"**{screen(session.language, 'conditions.list')}:**"]
        for number, condition in enumerate(conditions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {describe_condition(language, condition)}")
        option = draft.option(option_key) if option_key is not None else None
        self.info_embed.title = (
            screen(session.language, "conditions.title_option", name=option_name(option))
            if option is not None
            else screen(session.language, "conditions.title")
        )
        self.info_embed.description = "\n".join(lines)

        def after_for(index: int | None) -> AfterEdit:
            """The callback that shows this screen again once a modal is done, with `index` selected."""

            async def after(interaction: Interaction, problem: str | None) -> None:
                """Show this screen again once a modal is done, with `index` selected."""
                view = ItemConditionsView(session, item_id, option_key=option_key, active_index=index, error=problem)
                await show(interaction, view)

            return after

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
        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "edit",
            on_edit,
            label=screen(session.language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=0,
            disabled=not editable,
        )
        self.add_button(
            "delete",
            on_delete,
            label=screen(session.language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            row=0,
            disabled=active is None,
        )

        async def on_switch(interaction: Interaction) -> None:
            """Select another restriction."""
            if not conditions:
                return
            view = ItemConditionsView(session, item_id, option_key=option_key, active_index=int(switch_select.values[0]))
            await show(interaction, view)

        switch_select = self.add_select(
            "switch",
            on_switch,
            options=[
                SelectOption(
                    label=translate(language, f"builder.interactive.editor.condition_name.{condition.type.value}")[:100],
                    value=str(number),
                    default=number == active,
                )
                for number, condition in enumerate(conditions)
            ],
            placeholder=screen(
                session.language, "placeholders.switch_condition" if conditions else "placeholders.no_conditions"
            ),
            row=1,
            disabled=not conditions,
        )

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
            condition_type = ConditionType(add_select.values[0])
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

        add_select = self.add_select(
            "add",
            on_add,
            options=add_options,
            placeholder=screen(session.language, add_placeholder),
            row=2,
            disabled=limit_reached or not add_options,
        )
        self.set_error(error)


class QuestionsView(_InteractiveScreen):
    """Lists the questions of one form and lets the user add, change, delete and reorder them."""

    def __init__(
        self, session: BuilderSession, item_id: int, *, active_index: int | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the form, `active_index` the selected question and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        questions = draft.questions
        active = _clamp(active_index, len(questions))

        lines = [screen(session.language, "questions.description")]
        if questions:
            lines += ["", f"**{screen(session.language, 'questions.list')}:**"]
        for number, question in enumerate(questions):
            marker = BULLET_ACTIVE if number == active else BULLET
            lines.append(f"{marker} {describe_question(language, number + 1, question)}")
        self.info_embed.title = screen(session.language, "questions.title", name=draft_name(language, draft))
        self.info_embed.description = "\n".join(lines)

        def after_question() -> AfterQuestion:
            """Build the callback that returns to this list after a question was added or changed."""

            async def after(interaction: Interaction, index: int | None, problem: str | None) -> None:
                """Show the question list again with the changed question selected."""
                await show(interaction, QuestionsView(session, item_id, active_index=index, error=problem))

            return after

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

        self.add_button("back", on_back, label=_ts(session, "buttons.back"), style=ButtonStyle.gray, emoji="◀️", row=0)
        self.add_button(
            "add",
            on_add,
            label=screen(session.language, "buttons.question_add"),
            style=ButtonStyle.green,
            emoji="➕",
            row=0,
            disabled=len(questions) >= MAX_QUESTIONS_PER_FORM,
        )
        self.add_button(
            "edit",
            on_edit,
            label=screen(session.language, "buttons.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
            row=0,
            disabled=active is None,
        )
        self.add_button(
            "delete",
            on_delete,
            label=screen(session.language, "buttons.delete"),
            style=ButtonStyle.red,
            emoji="🗑️",
            row=0,
            disabled=active is None,
        )
        self.add_button(
            "up",
            on_up,
            label=_ts(session, "buttons.up"),
            style=ButtonStyle.blurple,
            emoji="⬆️",
            row=1,
            disabled=active is None or active <= 0,
        )
        self.add_button(
            "down",
            on_down,
            label=_ts(session, "buttons.down"),
            style=ButtonStyle.blurple,
            emoji="⬇️",
            row=1,
            disabled=active is None or active >= len(questions) - 1,
        )

        async def on_switch(interaction: Interaction) -> None:
            """Select another question."""
            if not questions:
                return
            await show(interaction, QuestionsView(session, item_id, active_index=int(switch_select.values[0])))

        switch_select = self.add_select(
            "switch",
            on_switch,
            options=[
                SelectOption(label=f"{number + 1}. {question.label}"[:100], value=str(number), default=number == active)
                for number, question in enumerate(questions)
            ],
            placeholder=screen(
                session.language, "placeholders.switch_question" if questions else "placeholders.no_questions"
            ),
            row=2,
            disabled=not questions,
        )
        self.set_error(error)
