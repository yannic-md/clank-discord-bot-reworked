from discord import Colour, Embed, Interaction
from discord.ui import Button
from discord.ui.select import BaseSelect
from discord.ui.view import BaseView

from core.i18n.translator import translate
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
from features.misc.builder.interactive.editor import BLANK_LINE, section_fields
from features.misc.builder.interactive.hub import element_name, placement_text
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.models import Action
from features.misc.builder.interactive.screens.action_editors import message_action_screen, role_action_screen
from features.misc.builder.interactive.screens.actions import actions_screen
from features.misc.builder.interactive.screens.conditions import conditions_screen
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

_PREFIX = "embed:interactive"
"""Every control of these screens carries this prefix in its `custom_id`, so that a click after a restart leaves the
preview alone (see the dead-interaction handling)."""


class EmbedHost(ViewHost[BuilderSession]):
    """Shows the screens of the editor in the embed builder."""

    def __init__(self, session: BuilderSession) -> None:
        """Create the host of one session."""
        super().__init__(session, _SCREENS)

    async def show(self, interaction: Interaction, view: BaseView) -> None:
        """Replace the screen that is shown with `view`."""
        assert isinstance(view, BuilderScreenView)
        await show(interaction, view)

    def placement_text(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the summary of the element tells it."""
        return describe_placement(self.session, item_id)

    def placement_label(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the list of the elements tells it."""
        return describe_placement(self.session, item_id)

    def delete_item(self, item_id: int) -> None:
        """Delete the element, also from the message."""
        delete_item(self.session, item_id)


class InteractiveScreenView(BuilderScreenView):
    """Base of the screens: one info embed, and controls that come from the description of the screen."""

    def __init__(self, session: BuilderSession) -> None:
        """Create an empty screen; `render` fills it."""
        super().__init__()
        self.session = session
        self.host = EmbedHost(session)
        self.info_embed: Embed = Embed(colour=Colour.blurple())
        self.content = None
        self.embeds = [self.info_embed]

    def render(self, page: Screen) -> None:
        """Draw the screen described by `page`: its texts in the info embed, its summary as fields, its controls as the
        children of the view, and its error - if there is one - as one more (red) embed."""
        embed = self.info_embed
        embed.title = page.title
        embed.description = page.body
        if page.sections is not None:
            embed.description = f"{page.body}\n{BLANK_LINE * page.gap}"
            for name, value, inline in section_fields(page.sections):
                embed.add_field(name=name, value=value, inline=inline)
        if page.warning:
            embed.colour = Colour.orange()

        for number, controls in sorted(page.rows.items()):
            for control in controls:
                item = control.item
                item.row = number
                is_link = isinstance(item, Button) and item.url is not None  # a link button has no `custom_id`
                if isinstance(item, Button | BaseSelect) and not is_link:
                    item.custom_id = f"{_PREFIX}:{type(self).__name__}:{control.name}"
                self.add_item(item)

        if page.error:
            self.embeds = [*self.embeds, Embed(description=page.error, colour=Colour.red())]


class InteractiveHubView(InteractiveScreenView):
    """The "Buttons & Dropdowns" screen: the clickable elements, and a button to create more."""

    def __init__(self, session: BuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error text to show."""
        super().__init__(session)
        self.render(hub_screen(self.host, error=error))


class ElementKindView(InteractiveScreenView):
    """Asks which kind of clickable element to create."""

    def __init__(self, session: BuilderSession, *, error: str | None = None) -> None:
        """`error` is an optional error text to show."""
        super().__init__(session)
        self.render(kinds_screen(self.host, error=error))


class FormView(InteractiveScreenView):
    """Everything about one form."""

    def __init__(self, session: BuilderSession, form_id: int, *, error: str | None = None) -> None:
        """`form_id` is the form and `error` an optional error text to show."""
        super().__init__(session)
        self.render(form_screen(self.host, form_id, error=error))


class OptionsView(InteractiveScreenView):
    """Lists the options of one dropdown."""

    def __init__(
        self, session: BuilderSession, item_id: int, *, active_key: str | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the dropdown, `active_key` the selected option and `error` an optional error text to show."""
        super().__init__(session)
        self.render(options_screen(self.host, item_id, active_key=active_key, error=error))


class ItemActionsView(InteractiveScreenView):
    """Lists the actions of one button (or dropdown option)."""

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
        self.render(actions_screen(self.host, item_id, option_key=option_key, active_index=active_index, error=error))


class RoleActionView(InteractiveScreenView):
    """The screen of a role action."""

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
        self.render(role_action_screen(self.host, item_id, option_key=option_key, index=index, action=action, error=error))


class MessageActionView(InteractiveScreenView):
    """The screen of a message action."""

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
        self.render(
            message_action_screen(self.host, item_id, option_key=option_key, index=index, action=action, error=error)
        )


class ItemConditionsView(InteractiveScreenView):
    """Lists the restrictions of one item (a dropdown option, or the dropdown as a whole)."""

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
        self.render(conditions_screen(self.host, item_id, option_key=option_key, active_index=active_index, error=error))


class QuestionsView(InteractiveScreenView):
    """Lists the questions of one form."""

    def __init__(
        self, session: BuilderSession, item_id: int, *, active_index: int | None = None, error: str | None = None
    ) -> None:
        """`item_id` is the form, `active_index` the selected question and `error` an optional error text to show."""
        super().__init__(session)
        self.render(questions_screen(self.host, item_id, active_index=active_index, error=error))


class PlacementView(InteractiveScreenView):
    """Lets the user choose where an item goes: a new row or a row with room left. The screen stays open while the
    item is moved around, and shows the items that are placed. While nothing is placed yet there is nothing to choose
    from, so the user is only asked whether to place the item at all."""

    def __init__(self, session: BuilderSession, item_id: int, *, error: str | None = None) -> None:
        """`item_id` is the item to place and `error` an optional error text to show."""
        super().__init__(session)
        language = session.language

        draft = session.library.get(item_id)
        assert draft is not None
        title = screen(language, "placement.title", name=element_name(language, draft))

        async def on_place(interaction: Interaction, target: str) -> None:
            """Put the item in the chosen place, or take it out of the message again - and show the result."""
            await self.host.placement(interaction, item_id, error=place_item(session, draft, target))

        async def on_back(interaction: Interaction) -> None:
            """Go back to the item list."""
            await self.host.hub(interaction)

        if not session.button_rows:
            page = Screen(title, screen(language, "placement.confirm"), error=error)
            add_confirmation(page, language, on_place, NEW_ROW_VALUE, on_back)
            self.render(page)
            return

        rows = preview_rows(session)
        # a message has five rows; the screen has room to preview fewer of them
        body = placement_text(
            language,
            translate(language, "builder.embed.info.placement.rows"),
            describe_layout(session),
            shown=PREVIEW_ROWS,
            total=len(rows),
        )
        page = Screen(title, body, error=error)
        add_back(page, self.host)
        add_row_movers(
            page, self.host, item_id, row_of(session, item_id), lambda offset: move_in_row(session, item_id, offset)
        )
        add_target_dropdown(page, language, placement_options(session, draft), on_place)
        add_previews(page, rows, PREVIEW_ROWS)
        self.render(page)


def _main_view(session: BuilderSession) -> BaseView:
    """The main screen of the embed builder (imported here: it leads to the screens above)."""
    from features.misc.builder.embed.views.gui import EmbedBuilderGUI

    return EmbedBuilderGUI(session)


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
)
"""The screens `EmbedHost` switches between."""
