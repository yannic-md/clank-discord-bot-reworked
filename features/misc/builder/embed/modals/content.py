from discord import Colour, Embed, Guild, Interaction, TextStyle
from discord.ui import Modal, TextInput

from core.discord_api.limits import (
    MAX_EMBED_DESCRIPTION,
    MAX_EMBED_TITLE,
    MAX_EMBED_URL,
    MAX_MESSAGE_CONTENT,
    MAX_MODAL_TEXTINPUT,
)
from core.i18n.translator import translate
from features.misc.builder.embed.session import BuilderSession
from features.misc.builder.embed.util.embed_ops import non_empty_embeds
from features.misc.builder.embed.validation import append_error, convert_to_role_mentions
from features.misc.builder.validation import convert_to_colour, is_valid_url

MAX_EMBED_DESCRIPTION_INPUT: int = min(MAX_EMBED_DESCRIPTION, MAX_MODAL_TEXTINPUT)


class MessageContentModal(Modal):
    """Modal to edit the plain text content of the message."""

    def __init__(self, session: BuilderSession) -> None:
        """Pre-fill the text field with the current message content."""
        super().__init__(title=translate(session.language, "builder.embed.modals.content.title"))
        self.session: BuilderSession = session

        # Plain `TextInput` (not wrapped in `Label`) so it uses the classic modal field
        # format, which reliably pre-fills `default` - the Components-V2 `Label`-wrapped
        # form does not currently prefill a `TextInput`'s value on some clients.
        self.content_input: TextInput = TextInput(
            label=translate(session.language, "builder.embed.modals.content.field"),
            style=TextStyle.paragraph,
            placeholder=translate(session.language, "builder.embed.modals.content.placeholder"),
            required=False,
            max_length=MAX_MESSAGE_CONTENT,
            default=session.content or None,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Store the content (turning `@RoleName` into real mentions) and return to the main screen."""
        content: str = self.content_input.value.strip()
        guild: Guild | None = interaction.guild
        if guild is not None:
            content = convert_to_role_mentions(content, guild)

        self.session.content = content
        from features.misc.builder.embed.views import EmbedBuilderGUI, show

        await show(interaction, EmbedBuilderGUI(self.session))


class EmbedTitleDescModal(Modal):
    """Modal to edit the title, description and title URL of the active embed."""

    def __init__(self, session: BuilderSession) -> None:
        """Pre-fill the fields with the active embed's values."""
        super().__init__(title=translate(session.language, "builder.embed.modals.title.title"))
        self.session: BuilderSession = session
        embed: Embed = session.active_embed

        self.name_input: TextInput = TextInput(
            label=translate(session.language, "builder.embed.modals.title.name.question"),
            placeholder=translate(session.language, "builder.embed.modals.title.name.placeholder"),
            required=False,
            max_length=MAX_EMBED_TITLE,
            default=embed.title or None,
        )

        self.description_input: TextInput = TextInput(
            label=translate(session.language, "builder.embed.modals.title.description.question"),
            placeholder=translate(session.language, "builder.embed.modals.title.description.placeholder"),
            style=TextStyle.paragraph,
            required=False,
            max_length=MAX_EMBED_DESCRIPTION_INPUT,
            default=embed.description or None,
        )

        self.url_input: TextInput = TextInput(
            label=translate(session.language, "builder.embed.modals.title.url.question"),
            placeholder=translate(session.language, "builder.embed.modals.title.url.placeholder"),
            required=False,
            max_length=MAX_EMBED_URL,
            default=embed.url or None,
        )

        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Validate the URL, apply title, description and URL to the active embed and return to the main screen."""
        from features.misc.builder.embed.views import EmbedBuilderGUI, show

        name: str = self.name_input.value.strip()
        description: str = self.description_input.value.strip()
        url: str = self.url_input.value.strip()

        if url and not is_valid_url(url):
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.embed.errors.invalid_url"),
            )
            return

        # Discord rejects a `url` on an embed that has neither a title nor a description
        # to attach it to (there'd be nothing for the link to make clickable).
        if url and not name and not description:
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.embed.errors.url_needs_title_or_description"),
            )
            return

        embed: Embed = self.session.active_embed
        embed.title = name or None
        embed.description = description or None
        embed.url = url or None
        await show(interaction, EmbedBuilderGUI(self.session))


class EmbedColourModal(Modal):
    """Modal to edit the colour of the active embed."""

    def __init__(self, session: BuilderSession) -> None:
        """Pre-fill the colour field with the active embed's colour."""
        super().__init__(title=translate(session.language, "builder.embed.modals.colour.title"))
        self.session: BuilderSession = session
        embed: Embed = session.active_embed

        self.colour_input: TextInput = TextInput(
            label=translate(session.language, "builder.embed.modals.colour.field"),
            placeholder=translate(session.language, "builder.modals.colour.placeholder"),
            required=False,
            max_length=32,
            default=str(embed.color) if embed.color else None,
        )
        self.add_item(self.colour_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Parse the colour (empty removes it), apply it to the active embed and return to the main screen."""
        from features.misc.builder.embed.views import EmbedBuilderGUI, show

        value: str = self.colour_input.value.strip()
        if not value:
            self.session.active_embed.colour = None
            await show(interaction, EmbedBuilderGUI(self.session))
            return

        try:
            colour: Colour = convert_to_colour(value)
        except ValueError:
            await append_error(
                interaction,
                non_empty_embeds(self.session.embeds),
                EmbedBuilderGUI(self.session),
                translate(self.session.language, "builder.errors.invalid_color"),
            )
            return

        embed: Embed = self.session.active_embed
        embed.colour = colour
        if not embed.title and not embed.description:
            # create placeholder embed to apply color, if no embed exists
            embed.title = translate(self.session.language, "builder.embed.placeholders.embed_placeholder_title")

        await show(interaction, EmbedBuilderGUI(self.session))
