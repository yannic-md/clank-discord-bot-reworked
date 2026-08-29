from discord import Embed, Interaction, RadioGroupOption, TextStyle
from discord.ui import Label, Modal, RadioGroup, TextInput

from core.discord_api.limits import MAX_EMBED_FIELD_NAME, MAX_EMBED_FIELD_VALUE
from core.i18n.translator import translate
from features.misc.embed_builder.session import BuilderSession


class EmbedFieldModal(Modal):
    def __init__(self, session: BuilderSession, field_index: int | None) -> None:
        super().__init__(title=translate(session.language, "builder.modals.field.title"))
        self.session: BuilderSession = session
        self.field_index: int | None = field_index

        embed: Embed = session.active_embed
        existing = embed.fields[field_index] if field_index is not None else None

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.field.name.question"),
            placeholder=translate(session.language, "builder.modals.field.name.placeholder"),
            max_length=MAX_EMBED_FIELD_NAME,
            default=existing.name if existing else None,
        )

        self.value_input: TextInput = TextInput(
            label=translate(session.language, "builder.modals.field.value.question"),
            placeholder=translate(session.language, "builder.modals.field.value.placeholder"),
            style=TextStyle.paragraph,
            max_length=MAX_EMBED_FIELD_VALUE,
            default=existing.value if existing else None,
        )

        self.inline_input: RadioGroup = RadioGroup(
            options=[
                RadioGroupOption(
                    label=translate(session.language, "builder.modals.field.inline_yes"),
                    value="yes",
                    default=bool(existing and existing.inline),
                ),
                RadioGroupOption(
                    label=translate(session.language, "builder.modals.field.inline_no"),
                    value="no",
                    default=bool(existing and not existing.inline),
                ),
            ]
        )

        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(Label(text=translate(session.language, "builder.modals.field.inline"), component=self.inline_input))

    async def on_submit(self, interaction: Interaction) -> None:
        from features.misc.embed_builder.views import EmbedFieldsView, show

        embed: Embed = self.session.active_embed
        name: str = self.name_input.value
        value: str = self.value_input.value
        inline: bool = self.inline_input.value == "yes"

        if self.field_index is None:
            embed.add_field(name=name, value=value, inline=inline)
            self.session.active_field = len(embed.fields) - 1
        else:
            embed.set_field_at(self.field_index, name=name, value=value, inline=inline)

        await show(interaction, EmbedFieldsView(self.session))
