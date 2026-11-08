from discord import Colour, Interaction, RadioGroupOption, SeparatorSpacing, TextStyle
from discord.ui import Label, Modal, RadioGroup, TextInput

from core.discord_api.limits import MAX_V2_TEXT_DISPLAY_LENGTH, MAX_V2_TOTAL_TEXT_LENGTH
from features.misc.builder.container.models import MAX_USER_COMPONENTS, ComponentKind, ComponentNode
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import t, ts
from features.misc.builder.container.util.tree import find_node, get_list, remaining_budget, total_text_length
from features.misc.builder.validation import convert_to_colour


class TextDisplayModal(Modal):
    def __init__(self, session: ContainerBuilderSession, *, parent_id: int | None, node_id: int | None) -> None:
        super().__init__(title=t(session.language, "modals.content.title"))
        self.session = session
        self.parent_id = parent_id
        self.node_id = node_id

        existing = find_node(session, node_id) if node_id is not None else None
        self.content_input: TextInput = TextInput(
            label=t(session.language, "modals.content.field"),
            style=TextStyle.paragraph,
            placeholder=t(session.language, "modals.content.placeholder"),
            required=True,
            max_length=MAX_V2_TEXT_DISPLAY_LENGTH,
            default=existing.content if existing else None,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.component_list import ComponentKindListView

        session = self.session
        content = self.content_input.value

        existing = find_node(session, self.node_id) if self.node_id is not None else None
        other_text_length = total_text_length(session.components) - (len(existing.content) if existing else 0)
        if other_text_length + len(content) > MAX_V2_TOTAL_TEXT_LENGTH:
            error = t(session.language, "errors.total_text", max=MAX_V2_TOTAL_TEXT_LENGTH)
            await show(
                interaction,
                ComponentKindListView(session, kind=ComponentKind.TEXT_DISPLAY, parent_id=self.parent_id, error=error),
            )
            return

        if existing is not None:
            existing.content = content
        else:
            owning_list = get_list(session, self.parent_id)
            new_node = ComponentNode(id=session.new_id(), kind=ComponentKind.TEXT_DISPLAY, content=content)
            owning_list.append(new_node)
            session.active_selection[(self.parent_id, ComponentKind.TEXT_DISPLAY)] = new_node.id

        await show(interaction, ComponentKindListView(session, kind=ComponentKind.TEXT_DISPLAY, parent_id=self.parent_id))


class ContainerModal(Modal):
    def __init__(self, session: ContainerBuilderSession, *, node_id: int | None) -> None:
        super().__init__(title=t(session.language, "modals.container.title"))
        self.session = session
        self.node_id = node_id

        existing = find_node(session, node_id) if node_id is not None else None
        self.colour_input: TextInput = TextInput(
            label=t(session.language, "modals.container.field"),
            placeholder=ts(session.language, "modals.colour.placeholder"),
            required=False,
            max_length=32,
            default=str(existing.accent_colour) if existing and existing.accent_colour else None,
        )
        self.spoiler_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(
                    label=ts(session.language, "modals.option_no"),
                    value="no",
                    default=not (existing.spoiler if existing else False),
                ),
                RadioGroupOption(
                    label=ts(session.language, "modals.option_yes"), value="yes", default=bool(existing and existing.spoiler)
                ),
            ]
        )
        self.add_item(self.colour_input)
        self.add_item(Label(text=t(session.language, "modals.spoiler.question"), component=self.spoiler_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.component_list import ComponentKindListView

        session = self.session
        colour_text = self.colour_input.value.strip()
        spoiler = self.spoiler_input.value == "yes"

        colour: Colour | None = None
        if colour_text:
            try:
                colour = convert_to_colour(colour_text)
            except ValueError:
                error = ts(session.language, "errors.invalid_color")
                await show(
                    interaction,
                    ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None, error=error),
                )
                return

        existing = find_node(session, self.node_id) if self.node_id is not None else None
        if existing is not None:
            existing.accent_colour = colour
            existing.spoiler = spoiler
        else:
            if remaining_budget(session) < 1:
                error = t(session.language, "errors.component_limit", limit=MAX_USER_COMPONENTS)
                await show(
                    interaction,
                    ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None, error=error),
                )
                return
            new_node = ComponentNode(
                id=session.new_id(), kind=ComponentKind.CONTAINER, accent_colour=colour, spoiler=spoiler
            )
            session.components.append(new_node)
            session.active_selection[(None, ComponentKind.CONTAINER)] = new_node.id

        await show(interaction, ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None))


class SeparatorModal(Modal):
    def __init__(self, session: ContainerBuilderSession, *, parent_id: int | None, node_id: int | None) -> None:
        super().__init__(title=t(session.language, "modals.separator.title"))
        self.session = session
        self.parent_id = parent_id
        self.node_id = node_id

        existing = find_node(session, node_id) if node_id is not None else None
        self.visible_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(
                    label=t(session.language, "modals.separator.visible"),
                    value="yes",
                    default=existing.visible if existing else True,
                ),
                RadioGroupOption(
                    label=t(session.language, "modals.separator.invisible"),
                    value="no",
                    default=existing is not None and not existing.visible,
                ),
            ]
        )
        self.spacing_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(
                    label=t(session.language, "modals.separator.small"),
                    value="small",
                    default=existing is None or existing.spacing == SeparatorSpacing.small,
                ),
                RadioGroupOption(
                    label=t(session.language, "modals.separator.large"),
                    value="large",
                    default=existing is not None and existing.spacing == SeparatorSpacing.large,
                ),
            ]
        )
        self.add_item(Label(text=t(session.language, "modals.separator.appearance"), component=self.visible_input))
        self.add_item(Label(text=t(session.language, "modals.separator.spacing"), component=self.spacing_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.builder.container.views.base import show
        from features.misc.builder.container.views.component_list import ComponentKindListView

        session = self.session
        visible = self.visible_input.value == "yes"
        spacing = SeparatorSpacing.large if self.spacing_input.value == "large" else SeparatorSpacing.small

        existing = find_node(session, self.node_id) if self.node_id is not None else None
        if existing is not None:
            existing.visible = visible
            existing.spacing = spacing
        else:
            if remaining_budget(session) < 1:
                error = t(session.language, "errors.component_limit", limit=MAX_USER_COMPONENTS)
                await show(
                    interaction,
                    ComponentKindListView(session, kind=ComponentKind.SEPARATOR, parent_id=self.parent_id, error=error),
                )
                return
            owning_list = get_list(session, self.parent_id)
            new_node = ComponentNode(id=session.new_id(), kind=ComponentKind.SEPARATOR, visible=visible, spacing=spacing)
            owning_list.append(new_node)
            session.active_selection[(self.parent_id, ComponentKind.SEPARATOR)] = new_node.id

        await show(interaction, ComponentKindListView(session, kind=ComponentKind.SEPARATOR, parent_id=self.parent_id))
