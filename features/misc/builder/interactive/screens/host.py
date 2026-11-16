from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from discord import Interaction
from discord.ui.view import BaseView

from features.misc.builder.interactive.models import Action, PayloadKind
from features.misc.builder.interactive.screens.spec import EditorSession


@dataclass(frozen=True, slots=True)
class ScreenClasses:
    """The classes a builder draws the screens of the editor with. Each is called with the session (the screens that
    are about an element: and the id of the element), plus the keywords of the screen."""

    main: Callable[..., BaseView]
    hub: Callable[..., BaseView]
    kinds: Callable[..., BaseView]
    form: Callable[..., BaseView]
    placement: Callable[..., BaseView]
    options: Callable[..., BaseView]
    actions: Callable[..., BaseView]
    role_action: Callable[..., BaseView]
    message_action: Callable[..., BaseView]
    conditions: Callable[..., BaseView]
    questions: Callable[..., BaseView]


class ViewHost[S: EditorSession](ABC):
    """Shows the screens of a builder, one at a time: each `show`-method builds the screen from the builder's own class
    and replaces the current one with it. What the builder does differently - how a screen is put on the message, where
    the message places an element - is left to the subclass."""

    def __init__(self, session: S, classes: ScreenClasses, template_kind: PayloadKind) -> None:
        """Create the host of one session; `classes` are the screens to show. `template_kind` is the kind of template
        (`EMBED` or `CONTAINER`) the builder makes: only those a message action can send."""
        self._session = session
        self._classes = classes
        self._template_kind = template_kind

    @property
    def session(self) -> S:
        """The session of the builder."""
        return self._session

    @property
    def template_kind(self) -> PayloadKind:
        """The kind of template the builder makes - and so the only kind its message actions offer to send."""
        return self._template_kind

    @abstractmethod
    async def show(self, interaction: Interaction, view: BaseView) -> None:
        """Replace the screen that is shown with `view`."""

    @abstractmethod
    def placement_text(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the summary of the element tells it - `None` if not placed."""

    @abstractmethod
    def placement_label(self, item_id: int) -> str | None:
        """Where the element sits in the message, as the list of the elements tells it - `None` if not placed."""

    @abstractmethod
    def delete_item(self, item_id: int) -> None:
        """Delete the element, also from the message."""

    async def main(self, interaction: Interaction) -> None:
        """Back to the main screen of the builder."""
        await self.show(interaction, self._classes.main(self.session))

    async def hub(self, interaction: Interaction, *, error: str | None = None) -> None:
        """The overview of the clickable elements."""
        await self.show(interaction, self._classes.hub(self.session, error=error))

    async def kinds(self, interaction: Interaction, *, error: str | None = None) -> None:
        """The choice of which kind of element to create."""
        await self.show(interaction, self._classes.kinds(self.session, error=error))

    async def form(self, interaction: Interaction, form_id: int, *, error: str | None = None) -> None:
        """A form."""
        await self.show(interaction, self._classes.form(self.session, form_id, error=error))

    async def placement(self, interaction: Interaction, item_id: int, *, error: str | None = None) -> None:
        """Where an element goes in the message."""
        await self.show(interaction, self._classes.placement(self.session, item_id, error=error))

    async def options(
        self, interaction: Interaction, item_id: int, *, active_key: str | None = None, error: str | None = None
    ) -> None:
        """The options of a dropdown."""
        await self.show(interaction, self._classes.options(self.session, item_id, active_key=active_key, error=error))

    async def actions(
        self,
        interaction: Interaction,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """The actions of an element (or of one option of a dropdown)."""
        view = self._classes.actions(self.session, item_id, option_key=option_key, active_index=active_index, error=error)
        await self.show(interaction, view)

    async def role_action(
        self,
        interaction: Interaction,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """A role action - `index` is its position, `action` the working copy so far."""
        view = self._classes.role_action(
            self.session, item_id, option_key=option_key, index=index, action=action, error=error
        )
        await self.show(interaction, view)

    async def message_action(
        self,
        interaction: Interaction,
        item_id: int,
        *,
        option_key: str | None = None,
        index: int | None = None,
        action: Action | None = None,
        error: str | None = None,
    ) -> None:
        """A message action - `index` is its position, `action` the working copy so far."""
        view = self._classes.message_action(
            self.session, item_id, option_key=option_key, index=index, action=action, error=error
        )
        await self.show(interaction, view)

    async def conditions(
        self,
        interaction: Interaction,
        item_id: int,
        *,
        option_key: str | None = None,
        active_index: int | None = None,
        error: str | None = None,
    ) -> None:
        """The restrictions of an element (or of one option of a dropdown)."""
        view = self._classes.conditions(self.session, item_id, option_key=option_key, active_index=active_index, error=error)
        await self.show(interaction, view)

    async def questions(
        self, interaction: Interaction, item_id: int, *, active_index: int | None = None, error: str | None = None
    ) -> None:
        """The questions of a form."""
        view = self._classes.questions(self.session, item_id, active_index=active_index, error=error)
        await self.show(interaction, view)


Host = ViewHost[EditorSession]
"""What the shared screens work with: any host, whatever kind of session its builder has."""
