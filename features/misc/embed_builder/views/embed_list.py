from discord import ButtonStyle, Colour, Embed, Interaction, SelectOption
from discord.ui import Button, Select, button, select

from core.discord_api.limits import MAX_EMBED_COUNT
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession
from features.misc.embed_builder.util.embed_ops import move_active_embed
from features.misc.embed_builder.validation import append_error
from features.misc.embed_builder.views.base import BuilderScreenView, create_embed_label, show


class EmbedListView(BuilderScreenView):
    def __init__(self, session: BuilderSession) -> None:
        super().__init__()
        self.session: BuilderSession = session

        self.info_embed: Embed = Embed(
            title=translate(session.language, "builder.info.embed_list.title"),
            description=translate(session.language, "builder.info.embed_list.description"),
            colour=Colour.blurple(),
        )
        self.content: str | None = None
        self.embeds: list[Embed] = [self.info_embed]

        self.back_button.label = translate(session.language, "builder.buttons.back")
        self.back_button.emoji = "◀️"
        self.add_button.label = translate(session.language, "builder.buttons.embed_add")
        self.remove_button.label = translate(session.language, "builder.buttons.embed_remove")
        self.add_button.emoji = "➕"
        self.remove_button.emoji = "➖"
        self.add_button.disabled = len(session.embeds) >= MAX_EMBED_COUNT
        self.remove_button.disabled = len(session.embeds) == 0

        if session.embeds:
            self.embed_select.disabled = False
            self.embed_select.placeholder = translate(session.language, "builder.placeholders.embed_list_select")
            self.embed_select.options = [
                SelectOption(
                    label=create_embed_label(session, embed, index + 1)[:100],
                    value=str(index),
                    default=index == session.active_embed_index,
                )
                for index, embed in enumerate(session.embeds)
            ]

            self.active_label.label = create_embed_label(session, session.active_embed, session.active_embed_index + 1)
            self.up_button.label = translate(session.language, "builder.buttons.up")
            self.up_button.emoji = "⬆️"
            self.down_button.label = translate(session.language, "builder.buttons.down")
            self.down_button.emoji = "⬇️"
            self.up_button.disabled = session.active_embed_index <= 0
            self.down_button.disabled = session.active_embed_index >= len(session.embeds) - 1
        else:
            self.embed_select.disabled = True
            self.embed_select.placeholder = translate(session.language, "builder.placeholders.embed_list_empty")
            self.embed_select.options = [SelectOption(label="—", value="__none__")]
            self.remove_item(self.active_label)
            self.remove_item(self.up_button)
            self.remove_item(self.down_button)

    @button(label="Back", style=ButtonStyle.gray, row=0, custom_id="embed_builder:list:back")
    async def back_button(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        from features.misc.embed_builder.views.gui import EmbedBuilderGUI

        await show(interaction, EmbedBuilderGUI(self.session))

    @button(label="Add", style=ButtonStyle.green, row=0, custom_id="embed_builder:list:add")
    async def add_button(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        if len(self.session.embeds) >= MAX_EMBED_COUNT:
            message = translate(self.session.language, "builder.errors.embed_limit", limit=MAX_EMBED_COUNT)
            await append_error(interaction, self.embeds, self, message)
            return

        # A bare `Embed()` has no visible content, so it'd stay invisible in the preview
        # until the user fills something in - give it the same placeholder the colour editor uses for the same reason.
        self.session.embeds.append(
            Embed(title=translate(self.session.language, "builder.placeholders.embed_placeholder_title"))
        )

        self.session.active_embed_index = len(self.session.embeds) - 1
        await show(interaction, EmbedListView(self.session))

    @button(label="Remove", style=ButtonStyle.red, row=0, custom_id="embed_builder:list:remove")
    async def remove_button(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        if not self.session.embeds:
            await show(interaction, EmbedListView(self.session))
            return

        del self.session.embeds[self.session.active_embed_index]
        self.session.active_embed_index = max(0, min(self.session.active_embed_index, len(self.session.embeds) - 1))
        await show(interaction, EmbedListView(self.session))

    @select(
        cls=Select,
        placeholder="Select an embed..",
        min_values=1,
        max_values=1,
        row=1,
        custom_id="embed_builder:list:select",
    )
    async def embed_select(self: EmbedListView, interaction: Interaction, select_obj: Select) -> None:
        self.session.active_embed_index = int(select_obj.values[0])
        await show(interaction, EmbedListView(self.session))

    @button(label="Active embed", style=ButtonStyle.gray, row=2, disabled=True)
    async def active_label(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        pass

    @button(label="Up", style=ButtonStyle.blurple, row=2, custom_id="embed_builder:list:up")
    async def up_button(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        move_active_embed(self.session, -1)
        await show(interaction, EmbedListView(self.session))

    @button(label="Down", style=ButtonStyle.blurple, row=2, custom_id="embed_builder:list:down")
    async def down_button(self: EmbedListView, interaction: Interaction, _button: Button) -> None:
        move_active_embed(self.session, 1)
        await show(interaction, EmbedListView(self.session))
