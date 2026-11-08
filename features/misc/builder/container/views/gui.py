from discord import ButtonStyle, Colour, Interaction, SelectOption
from discord.ui import ActionRow, Container, TextDisplay

from features.misc.builder.container.modals.webhook import ChannelModal
from features.misc.builder.container.models import (
    ALLOWED_CHILD_KINDS,
    KIND_EMOJIS,
    MESSAGE_CONTENT_EMOJI,
    MESSAGE_CONTENT_VALUE,
    ORDER_VALUE,
    ComponentKind,
)
from features.misc.builder.container.session import ContainerBuilderSession
from features.misc.builder.container.translations import kind_label, t, ts
from features.misc.builder.container.util.render import build_items
from features.misc.builder.container.util.templates import load_user_templates
from features.misc.builder.container.util.tree import content_nodes, count_by_kind, non_empty_nodes
from features.misc.builder.container.views.base import BuilderLayoutView, add_button, add_select, info_container, show


class MainView(BuilderLayoutView):
    def __init__(self, session: ContainerBuilderSession, *, error: str | None = None, notice: str | None = None) -> None:
        from features.misc.builder.container.views.component_list import ComponentKindListView
        from features.misc.builder.container.views.order import ComponentOrderView
        from features.misc.builder.container.views.send import SendConfirmView, save_message_changes
        from features.misc.builder.container.views.templates import TemplatesView
        from features.misc.builder.container.views.webhook import WebhookView

        super().__init__()
        self.session = session

        for item in build_items(non_empty_nodes(session.components)):
            self.add_item(item)

        nav_row: ActionRow = ActionRow()

        async def on_send(interaction: Interaction) -> None:
            if not non_empty_nodes(session.components):
                error = t(session.language, "errors.nothing_to_send")
                await show(interaction, MainView(session, error=error))
                return
            await show(interaction, SendConfirmView(session))

        async def on_webhook(interaction: Interaction) -> None:
            await show(interaction, WebhookView(session))

        async def on_channel(interaction: Interaction) -> None:
            await interaction.response.send_modal(ChannelModal(session))

        async def on_templates(interaction: Interaction) -> None:
            session.templates = await load_user_templates(session.slashcmd_author_id)
            await show(interaction, TemplatesView(session))

        async def on_save(interaction: Interaction) -> None:
            await save_message_changes(interaction, session, self)

        if session.edit_mode:
            # Editing one of the bot's own messages in place: nothing to send, so no webhook/channel either.
            add_button(
                nav_row, on_save, label=ts(session.language, "buttons.edit_save"), style=ButtonStyle.green, emoji="💾"
            )
        else:
            add_button(nav_row, on_send, label=ts(session.language, "buttons.send"), style=ButtonStyle.green, emoji="📨")
            can_manage_webhooks = session.target_channel.permissions_for(session.slashcmd_author).manage_webhooks
            add_button(
                nav_row,
                on_webhook,
                label=ts(session.language, "buttons.webhook"),
                style=ButtonStyle.blurple,
                emoji="📢",
                disabled=not can_manage_webhooks,
            )
            if session.channel is not None:
                channel_label = f"#{session.channel.name}"[:80]  # show the chosen channel's name
                add_button(nav_row, on_channel, label=channel_label, style=ButtonStyle.gray)
            else:
                add_button(
                    nav_row,
                    on_channel,
                    label=ts(session.language, "buttons.channel"),
                    style=ButtonStyle.gray,
                    emoji="🔗",
                )
        add_button(nav_row, on_templates, label=ts(session.language, "buttons.templates"), style=ButtonStyle.red, emoji="📂")
        self.add_item(nav_row)

        select_row: ActionRow = ActionRow()
        container_count = count_by_kind(session.components, ComponentKind.CONTAINER)
        options = [
            SelectOption(
                label=f"{kind_label(session.language, ComponentKind.CONTAINER)} ({container_count})",
                description=t(session.language, "select.container.description"),
                value=ComponentKind.CONTAINER.value,
                emoji=KIND_EMOJIS[ComponentKind.CONTAINER],
            ),
            SelectOption(
                label=f"{t(session.language, 'select.content.label')} ({len(content_nodes(session.components))})",
                description=t(session.language, "select.content.description"),
                value=MESSAGE_CONTENT_VALUE,
                emoji=MESSAGE_CONTENT_EMOJI,
            ),
            SelectOption(
                label=t(session.language, "select.order.label"),
                description=t(session.language, "select.order.description"),
                value=ORDER_VALUE,
                emoji="🔀",
            ),
        ]

        async def on_select(interaction: Interaction) -> None:
            value = component_select.values[0]
            if value == MESSAGE_CONTENT_VALUE:
                await show(interaction, MessageContentView(session))
                return
            if value == ORDER_VALUE:
                await show(interaction, ComponentOrderView(session, parent_id=None))
                return
            await show(interaction, ComponentKindListView(session, kind=ComponentKind.CONTAINER, parent_id=None))

        component_select = add_select(
            select_row, on_select, options=options, placeholder=ts(session.language, "select.placeholder")
        )
        self.add_item(select_row)

        if notice:
            self.add_status(Container(TextDisplay(notice), accent_colour=Colour.orange()))
        if error:
            self.add_error(error)


class MessageContentView(BuilderLayoutView):
    """Hub for components that sit directly in the message (outside of any container)."""

    def __init__(self, session: ContainerBuilderSession) -> None:
        from features.misc.builder.container.views.component_list import ComponentKindListView
        from features.misc.builder.container.views.order import ComponentOrderView

        super().__init__()
        self.session = session

        header = f"### {MESSAGE_CONTENT_EMOJI} ~ {t(session.language, 'select.content.label')}"
        description = t(session.language, "info.content.description")
        self.add_item(info_container(f"{header}\n{description}"))

        nav_row: ActionRow = ActionRow()

        async def on_back(interaction: Interaction) -> None:
            await show(interaction, MainView(session))

        add_button(nav_row, on_back, label=ts(session.language, "buttons.back"), style=ButtonStyle.gray, emoji="◀️")

        async def on_order(interaction: Interaction) -> None:
            await show(interaction, ComponentOrderView(session, parent_id=None, content_only=True))

        content_count = len(content_nodes(session.components))
        add_button(
            nav_row,
            on_order,
            label=t(session.language, "buttons.order"),
            style=ButtonStyle.gray,
            emoji="🔀",
            disabled=content_count < 2,
        )
        self.add_item(nav_row)

        options = [
            SelectOption(
                label=f"{kind_label(session.language, kind)} ({sum(1 for node in session.components if node.kind == kind)})",
                description=t(session.language, f"select.{kind.value}.description"),
                value=kind.value,
                emoji=KIND_EMOJIS[kind],
            )
            for kind in ALLOWED_CHILD_KINDS
        ]

        async def on_select(interaction: Interaction) -> None:
            value = content_select.values[0]
            await show(interaction, ComponentKindListView(session, kind=ComponentKind(value), parent_id=None))

        select_row: ActionRow = ActionRow()
        content_select = add_select(
            select_row, on_select, options=options, placeholder=t(session.language, "placeholders.content_select")
        )
        self.add_item(select_row)
