from discord import Colour, Interaction
from discord.ui import ActionRow, Container, TextDisplay
from discord.ui.view import BaseView

from features.misc.builder.container.models import ComponentKind
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t
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
    info_separator,
    sections_container,
    show,
)
from features.misc.builder.interactive.hub import element_name
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.models import Action, PayloadKind
from features.misc.builder.interactive.payload import OutgoingMessage
from features.misc.builder.interactive.screens.action_editors import message_action_screen, role_action_screen
from features.misc.builder.interactive.screens.actions import actions_screen
from features.misc.builder.interactive.screens.conditions import conditions_screen
from features.misc.builder.interactive.screens.controls import Callback, back_button
from features.misc.builder.interactive.screens.host import ScreenClasses, ViewHost
from features.misc.builder.interactive.screens.hub import form_screen, hub_screen, kinds_screen
from features.misc.builder.interactive.screens.options import options_screen
from features.misc.builder.interactive.screens.placement import (
    add_back,
    add_confirmation,
    add_previews,
    add_row_movers,
    add_target_dropdown,
)
from features.misc.builder.interactive.screens.questions import questions_screen
from features.misc.builder.interactive.screens.spec import Screen


class ContainerHost(ViewHost[ContainerBuilderSession]):
    """Shows the screens of the editor in the container builder."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        """Create the host of one session."""
        super().__init__(session, _SCREENS, PayloadKind.CONTAINER)

    async def show(self, interaction: Interaction, view: BaseView) -> None:
        """Replace the screen that is shown with `view`."""
        assert isinstance(view, BuilderLayoutView)
        await show(interaction, view)

    def placement_text(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the summary of the element tells it."""
        return describe_placement(self.session, item_id)

    def placement_label(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the list of the elements tells it."""
        return placement_label(self.session, item_id)

    def delete_item(self, item_id: int) -> None:
        """Delete the element, also from the message."""
        delete_item(self.session, item_id)


class InteractiveLayoutView(BuilderLayoutView):
    """Base of the screens: a container with the texts, and a row of controls for each row of the description."""

    notes: str | None = None
    """A text for below a divider line in the container of the screen, if it has one."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        """Create an empty screen; `render` fills it."""
        super().__init__()
        self.session = session
        self.host = ContainerHost(session)

    def text_box(self, page: Screen) -> Container:
        """The container with the texts of the screen described by `page`."""
        heading = f"### {page.title}\n{page.body}"
        if page.sections is not None:
            box = sections_container(heading, page.sections, spaced=page.spaced)
        else:
            box = Container(TextDisplay(heading), accent_colour=Colour.orange() if page.warning else Colour.blurple())
        if self.notes:
            box.add_item(info_separator())
            box.add_item(TextDisplay(self.notes))
        return box

    def render(self, page: Screen) -> None:
        """Draw the screen described by `page`: its texts in a container, a row of controls for each of its rows, and
        its error - if there is one - in a red box."""
        self.add_item(self.text_box(page))
        self.add_controls(page)
        if page.error:
            self.add_error(page.error)

    def add_controls(self, page: Screen) -> None:
        """Put the controls of `page` on the screen, a row of them for each of its rows."""
        for _, controls in sorted(page.rows.items()):
            self.add_item(ActionRow(*(control.item for control in controls)))


class InteractiveHubView(InteractiveLayoutView):
    """The "Buttons & Dropdowns" screen: the clickable elements, and a button to create more."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error box to show."""
        super().__init__(session)
        self.render(hub_screen(self.host, error=error))


class ElementKindView(InteractiveLayoutView):
    """Asks which kind of clickable element to create."""

    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error box to show."""
        super().__init__(session)
        self.render(kinds_screen(self.host, error=error))


class FormView(InteractiveLayoutView):
    """Everything about one form."""

    def __init__(self, session: ContainerBuilderSession, form_id: int, *, error: str | None = None) -> None:
        """`form_id` is the form and `error` an optional error box to show."""
        super().__init__(session)
        self.render(form_screen(self.host, form_id, error=error))


class OptionsView(InteractiveLayoutView):
    """Lists the options of one dropdown."""

    def __init__(
        self, session: ContainerBuilderSession, item_id: int, *, active_key: str | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the dropdown, `active_key` the selected option and `error` an optional error box to show."""
        super().__init__(session)
        self.render(options_screen(self.host, item_id, active_key=active_key, error=error))


class ItemActionsView(InteractiveLayoutView):
    """Lists the actions of one button (or dropdown option)."""

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
        super().__init__(session)
        self.render(actions_screen(self.host, item_id, option_key=option_key, active_index=active_index, error=error))


class RoleActionView(InteractiveLayoutView):
    """The screen of a role action."""

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
        super().__init__(session)
        self.render(role_action_screen(self.host, item_id, option_key=option_key, index=index, action=action, error=error))


class MessageActionView(InteractiveLayoutView):
    """The screen of a message action."""

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
        super().__init__(session)
        self.render(
            message_action_screen(self.host, item_id, option_key=option_key, index=index, action=action, error=error)
        )


class TemplatePreviewView(InteractiveLayoutView):
    """A template's message on a screen of its own: its components as they are sent, and below them a row with one
    button to go back. The row takes two of the 40 components a message may have; the template never has more than
    `MAX_USER_COMPONENTS` (33), so there is always room for them."""

    def __init__(self, session: ContainerBuilderSession, message: OutgoingMessage, back: Callback) -> None:
        """`message` is what the template makes and `back` runs when the button is pressed."""
        super().__init__(session)
        assert message.view is not None, "a container template makes a Components V2 message"
        components = list(message.view.children)
        message.view.clear_items()
        for component in components:
            self.add_item(component)

        page = Screen("", "")
        page.add(0, back_button(session.language, back))
        self.add_controls(page)


class ItemConditionsView(InteractiveLayoutView):
    """Lists the restrictions of one item (a dropdown option, or the dropdown as a whole)."""

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
        super().__init__(session)
        self.render(conditions_screen(self.host, item_id, option_key=option_key, active_index=active_index, error=error))


class QuestionsView(InteractiveLayoutView):
    """Lists the questions of one form."""

    def __init__(
        self, session: ContainerBuilderSession, item_id: int, *, active_index: int | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the form, `active_index` the selected question and `error` an optional error box to show."""
        super().__init__(session)
        self.render(questions_screen(self.host, item_id, active_index=active_index, error=error))


class PlacementView(InteractiveLayoutView):
    """Lets the user choose where an item goes: a new row, a row with room, or next to a text. The screen stays open
    while the item is moved around, and shows the items that are placed. While nothing is placed yet and the message
    has just one place to offer, there is nothing to choose from, so the user is only asked whether to place the item
    at all."""

    def __init__(self, session: ContainerBuilderSession, item_id: int, *, error: str | None = None) -> None:
        """`item_id` is the item to place and `error` an optional error box to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.require(item_id)
        title = screen(language, "placement.title", name=element_name(language, draft))
        options = placement_options(session, draft)

        async def on_place(interaction: Interaction, target: str) -> None:
            """Put the item in the chosen place, or take it out of the message again - and show the result."""
            await self.host.placement(interaction, item_id, error=place_item(session, draft, target))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the item list."""
            await self.host.hub(interaction)

        if not has_placed_items(session) and [option.value for option in options] == [NEW_ROW_MESSAGE_VALUE]:
            page = Screen(title, screen(language, "placement.confirm"), error=error)
            add_confirmation(page, language, on_place, NEW_ROW_MESSAGE_VALUE, on_back)
            self.render(page)
            return

        placement = find_placement(session, item_id)
        rows = preview_rows(session)

        # What the screen is for and where a button may go; below a divider, the message the buttons are placed in: a
        # button can go anywhere in it, so what it is made of is what makes the places clear.
        page = Screen(
            title, f"{screen(language, 'placement.description')}\n\n{t(language, 'info.placement.rows')}", error=error
        )
        outline = message_outline(session, marked=item_id)
        if outline:
            notes = [f"**{t(language, 'info.placement.outline')}:**", outline]
            if placement is not None:
                notes += ["", t(language, "info.placement.marked")]
            if len(rows) > PREVIEW_ROWS:  # the screen has room to preview only some of the rows
                notes += ["", t(language, "info.placement.preview_truncated", shown=PREVIEW_ROWS, total=len(rows))]
            self.notes = "\n".join(notes)

        add_back(page, self.host)
        in_row = placement is not None and placement.node.kind == ComponentKind.ACTION_ROW
        neighbours = placement.node.item_ids if placement is not None and in_row else []
        add_row_movers(page, self.host, item_id, neighbours, lambda offset: move_in_row(session, item_id, offset))
        add_target_dropdown(page, language, options, on_place)
        add_previews(page, rows, PREVIEW_ROWS)
        self.render(page)


def _main_view(session: ContainerBuilderSession) -> BaseView:
    """The main screen of the container builder (imported here: it leads to the screens above)."""
    from features.misc.builder.container.views.gui import MainView

    return MainView(session)


_SCREENS = ScreenClasses(
    main=_main_view,
    hub=InteractiveHubView,
    kinds=ElementKindView,
    form=FormView,
    placement=PlacementView,
    options=OptionsView,
    actions=ItemActionsView,
    role_action=RoleActionView,
    message_action=MessageActionView,
    conditions=ItemConditionsView,
    questions=QuestionsView,
    template_preview=TemplatePreviewView,
)
"""The screens `ContainerHost` switches between."""
