from abc import ABC, abstractmethod

from discord import ButtonStyle, Interaction, Member, Role
from discord.app_commands import AppCommandChannel, AppCommandThread

from features.misc.builder.channels import can_post_in, resolve_selected_channel
from features.misc.builder.interactive.action_screens import (
    MESSAGE_TYPES,
    ROLE_TYPES,
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
    template_message,
    type_options,
    variables_help,
    with_channel,
    with_payload,
    with_roles,
    with_type,
)
from features.misc.builder.interactive.messages import common, t
from features.misc.builder.interactive.modals import MessageContentModal
from features.misc.builder.interactive.models import Action, ActionType, MessagePayload
from features.misc.builder.interactive.screens.common import item_scope
from features.misc.builder.interactive.screens.controls import (
    back_button,
    button,
    channel_picker,
    dropdown,
    role_picker,
    save_button,
    template_preview_button,
)
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen
from features.misc.builder.interactive.templates import load_template_choices


class _ActionEditor(ABC):
    """What the screens of a role action and of a message action have in common: a working copy of the action, leaving
    without saving, saving, and turning the action into one of another type."""

    def __init__(self, host: Host, item_id: int, option_key: str | None, index: int | None, action: Action | None) -> None:
        """`option_key` is the option of a dropdown the action belongs to, `index` the position of the action to change
        (`None` for a new one) and `action` the working copy so far, if there is one."""
        self.host = host
        self.item_id = item_id
        self.option_key = option_key
        self.index = index
        self.language = host.session.language
        self.draft, self.config, self.inherited = item_scope(host.session, item_id, option_key)
        if action is None:
            action = self.config.actions[index] if index is not None else self.new_action()
        self.working: Action = action

    @abstractmethod
    def new_action(self) -> Action:
        """The action a screen for a new action starts with."""

    @abstractmethod
    async def again(self, interaction: Interaction, updated: Action, problem: str | None = None) -> None:
        """Show this screen once more, with `updated` as the working copy and - if there is one - a problem to tell."""

    async def on_back(self, interaction: Interaction) -> None:
        """Leave without saving."""
        await self.host.actions(interaction, self.item_id, option_key=self.option_key, active_index=self.index)

    async def on_save(self, interaction: Interaction) -> None:
        """Store the action - or say what is wrong with it."""
        problem = save_action(
            self.language, self.config, self.inherited, self.index, self.working, in_form=self.draft.is_form
        )
        if problem is not None:
            await self.again(interaction, self.working, problem)
            return
        position = self.index if self.index is not None else len(self.config.actions) - 1
        await self.host.actions(interaction, self.item_id, option_key=self.option_key, active_index=position)

    async def on_type(self, interaction: Interaction, values: list[str]) -> None:
        """Turn the action into another type - unless it would contradict the other actions."""
        changed = with_type(self.working, ActionType(values[0]))
        problem = clash_problem(self.language, self.config, self.index, changed, self.inherited)
        await self.again(interaction, self.working if problem else changed, problem)


class _RoleEditor(_ActionEditor):
    """The working copy of a role action."""

    def new_action(self) -> Action:
        """The action a screen for a new action starts with: one that adds roles."""
        return Action(ActionType.ROLE_ADD)

    async def again(self, interaction: Interaction, updated: Action, problem: str | None = None) -> None:
        """Show this screen once more, with `updated` as the working copy and - if there is one - a problem to tell."""
        await self.host.role_action(
            interaction, self.item_id, option_key=self.option_key, index=self.index, action=updated, error=problem
        )

    async def on_roles(self, interaction: Interaction, picked: list[Role]) -> None:
        """The roles of the action were picked - if this user may hand them out."""
        guild, member = interaction.guild, interaction.user
        assert guild is not None and isinstance(member, Member)
        problem = chosen_role_problem(self.language, picked, member, guild)
        if problem is not None:
            await self.again(interaction, self.working, problem)
            return
        chosen = with_roles(self.working, [role.id for role in picked])
        problem = clash_problem(self.language, self.config, self.index, chosen, self.inherited)
        await self.again(interaction, self.working if problem else chosen, problem)


class _MessageEditor(_ActionEditor):
    """The working copy of a message action."""

    def new_action(self) -> Action:
        """The action a screen for a new action starts with: a reply with a sample message."""
        return new_message_action(self.language, self.config)

    async def again(self, interaction: Interaction, updated: Action, problem: str | None = None) -> None:
        """Show this screen once more, with `updated` as the working copy and - if there is one - a problem to tell."""
        await self.host.message_action(
            interaction, self.item_id, option_key=self.option_key, index=self.index, action=updated, error=problem
        )

    async def after_content(self, interaction: Interaction, payload: MessagePayload | None, problem: str | None) -> None:
        """Take the message over once its modal is done."""
        if problem is not None or payload is None:
            await self.again(interaction, self.working, problem)
            return
        await self.again(interaction, with_payload(self.working, payload))

    async def on_content(self, interaction: Interaction) -> None:
        """Open the modal to write the message - with the templates of this builder to choose from."""
        templates = await load_template_choices(interaction.user.id, self.host.template_kind)
        await interaction.response.send_modal(
            MessageContentModal(self.language, self.working.payload, templates, self.after_content)
        )

    def questions(self) -> list[str]:
        """The questions of the form the action belongs to - none if it is not in a form."""
        return [question.label for question in self.draft.questions] if self.draft.is_form else []

    def has_template(self) -> bool:
        """Whether the message is a template of the kind this builder makes - the one a preview can show."""
        payload = self.working.payload
        return payload is not None and payload.kind is self.host.template_kind

    async def on_preview(self, interaction: Interaction) -> None:
        """Show the template of the message on a screen of its own - or say why that is not possible."""
        payload = self.working.payload
        if payload is None or not self.has_template():
            await self.again(interaction, self.working)
            return

        session = self.host.session
        message = template_message(
            self.language, payload, session.slashcmd_author, session.slashcmd_channel, self.questions()
        )
        if message is None:
            await self.again(interaction, self.working, common(self.language, "info.preview.empty"))
            return
        await self.host.template_preview(interaction, message, self.on_preview_back)

    async def on_preview_back(self, interaction: Interaction) -> None:
        """Leave the preview and go back to the message action - as it was left."""
        await self.again(interaction, self.working)

    async def on_channel(self, interaction: Interaction, picked: list[AppCommandChannel | AppCommandThread]) -> None:
        """The channel of a channel message was picked - if this user may write there."""
        member = interaction.user
        assert isinstance(member, Member)
        channel = await resolve_selected_channel(picked[0])
        if not can_post_in(channel, member):
            problem = t(self.language, "errors.channel_no_access", channel=channel.mention)
            await self.again(interaction, self.working, problem)
            return
        await self.again(interaction, with_channel(self.working, channel.id))


def role_action_screen(
    host: Host,
    item_id: int,
    *,
    option_key: str | None = None,
    index: int | None = None,
    action: Action | None = None,
    error: str | None = None,
) -> Screen:
    """The screen of a role action: what it does to the roles (add, remove, toggle, set) and which roles.

    `index` is the position of the action to change (`None` for a new one) and `action` the working copy so far."""
    language = host.session.language
    editor = _RoleEditor(host, item_id, option_key, index, action)
    working = editor.working

    title, description = screen_texts(language, working)
    page = Screen(title, description, sections=role_sections(language, working))
    page.add(0, back_button(language, editor.on_back))
    page.add(0, save_button(language, editor.on_save))
    page.add(
        1,
        dropdown(
            "type",
            editor.on_type,
            options=type_options(language, ROLE_TYPES, working.type, len(working.roles)),
            placeholder=t(language, "action_screen.type_placeholder"),
        ),
    )
    page.add(2, role_picker("roles", role_select(language, working), editor.on_roles))
    page.error = error
    return page


def message_action_screen(
    host: Host,
    item_id: int,
    *,
    option_key: str | None = None,
    index: int | None = None,
    action: Action | None = None,
    error: str | None = None,
) -> Screen:
    """The screen of a message action: how the message reaches people (reply, direct message, channel message), what
    it says and - for a channel message - where it goes.

    `index` is the position of the action to change (`None` for a new one) and `action` the working copy so far."""
    session = host.session
    language = session.language
    editor = _MessageEditor(host, item_id, option_key, index, action)
    working = editor.working

    title, description = screen_texts(language, working)
    in_form = editor.draft.is_form
    preview = message_preview(language, session.slashcmd_author, session.slashcmd_channel, editor.questions())
    page = Screen(
        title,
        f"{description}\n\n{variables_help(language, in_form=in_form)}",
        sections=message_sections(language, working, preview=preview),
    )
    page.add(0, back_button(language, editor.on_back))
    page.add(
        0,
        button(
            "content",
            editor.on_content,
            label=t(language, "action_screen.message.edit"),
            style=ButtonStyle.blurple,
            emoji="✏️",
        ),
    )
    if editor.has_template():
        page.add(0, template_preview_button(language, editor.on_preview))
    page.add(0, save_button(language, editor.on_save))
    page.add(
        1,
        dropdown(
            "type",
            editor.on_type,
            options=type_options(language, MESSAGE_TYPES, working.type),
            placeholder=t(language, "action_screen.type_placeholder"),
        ),
    )
    if working.type is ActionType.SEND_CHANNEL:
        page.add(2, channel_picker("channel", channel_select(language, working), editor.on_channel))
    page.error = error
    return page
