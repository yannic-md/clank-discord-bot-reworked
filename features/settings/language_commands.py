from discord import Interaction
from discord.app_commands import (
    Choice,
    Group,
    allowed_installs,
    checks,
    choices,
    default_permissions,
    describe,
    guild_only,
    rename,
)
from discord.ext.commands import AutoShardedBot, Cog

from core.db.repositories.language.guild_language_repository import get_guild_language, set_guild_language
from core.db.repositories.language.user_language_repository import get_user_language, set_user_language
from core.enums.language import SupportedLanguage
from core.i18n.discord_translator import cmd
from core.i18n.translator import translate


class LanguageSettings(Cog):
    guild_lang: Group = Group(
        name=cmd("commands.guild_language.group.name"),
        description=cmd("commands.guild_language.group.description"),
        guild_only=True,
    )
    user_lang: Group = Group(
        name=cmd("commands.user_language.group.name"), description=cmd("commands.user_language.group.description")
    )

    def __init__(self, client: AutoShardedBot) -> None:
        self.client = client

    @guild_lang.command(
        name=cmd("commands.guild_language.show.name"), description=cmd("commands.guild_language.show.description")
    )
    @allowed_installs(guilds=True, users=False)
    @default_permissions(manage_guild=True)
    @checks.has_permissions(manage_guild=True)
    @guild_only()
    async def show(self, interaction: Interaction) -> None:
        """Reply with the language currently configured for the invoking guild.

        Args:
            interaction (Interaction): The interaction of the slash command invocation.
        """
        assert interaction.guild_id is not None

        language: SupportedLanguage = await get_guild_language(interaction.guild_id)
        language_name: str = translate(language, f"common.language.{language.value}")
        await interaction.response.send_message(
            translate(language, "settings.guild_language.show.current", language=language_name.upper()), ephemeral=True
        )

    @guild_lang.command(
        name=cmd("commands.guild_language.set.name"), description=cmd("commands.guild_language.set.description")
    )
    @rename(language=cmd("commands.guild_language.set.parameter.name"))
    @describe(language=cmd("commands.guild_language.set.parameter.description"))
    @choices(
        language=[
            Choice(name="🇩🇪 " + str(cmd("common.language.de")), value=SupportedLanguage.GERMAN.value),
            Choice(name="🇺🇸 " + str(cmd("common.language.en")), value=SupportedLanguage.ENGLISH.value),
        ]
    )
    @allowed_installs(guilds=True, users=False)
    @default_permissions(manage_guild=True)
    @checks.has_permissions(manage_guild=True)
    @guild_only()
    async def set(self, interaction: Interaction, language: SupportedLanguage) -> None:
        """Persist a new language for the invoking guild and confirm the change.

        Args:
            interaction (Interaction): The interaction of the slash command invocation.
            language (SupportedLanguage): The language to store for the guild.
        """
        assert interaction.guild_id is not None

        await set_guild_language(interaction.guild_id, language)
        language_name: str = translate(language, f"common.language.{language.value}")
        await interaction.response.send_message(
            translate(language, "settings.guild_language.set.success", language=language_name.upper()), ephemeral=True
        )

    #
    #
    ##                                          USER LANGUAGE
    #
    #

    @user_lang.command(
        name=cmd("commands.user_language.show.name"), description=cmd("commands.user_language.show.description")
    )
    @allowed_installs(guilds=True, users=True)
    @guild_only()
    async def user_show(self, interaction: Interaction) -> None:
        """Reply with the language currently configured for the invoking user.

        Args:
            interaction (Interaction): The interaction of the slash command invocation.
        """

        language: SupportedLanguage = await get_user_language(interaction.user.id)
        language_name: str = translate(language, f"common.language.{language.value}")
        await interaction.response.send_message(
            translate(language, "settings.user_language.show.current", language=language_name.upper()), ephemeral=True
        )

    @user_lang.command(
        name=cmd("commands.user_language.set.name"), description=cmd("commands.user_language.set.description")
    )
    @rename(language=cmd("commands.user_language.set.parameter.name"))
    @describe(language=cmd("commands.user_language.set.parameter.description"))
    @choices(
        language=[
            Choice(name="🇩🇪 " + str(cmd("common.language.de")), value=SupportedLanguage.GERMAN.value),
            Choice(name="🇺🇸 " + str(cmd("common.language.en")), value=SupportedLanguage.ENGLISH.value),
        ]
    )
    @allowed_installs(guilds=True, users=True)
    @guild_only()
    async def user_set(self, interaction: Interaction, language: SupportedLanguage) -> None:
        """Persist a new language for the invoking user and confirm the change.

        Args:
            interaction (Interaction): The interaction of the slash command invocation.
            language (SupportedLanguage): The language to store for the user.
        """

        await set_user_language(interaction.user.id, language)
        language_name: str = translate(language, f"common.language.{language.value}")
        await interaction.response.send_message(
            translate(language, "settings.user_language.set.success", language=language_name.upper()), ephemeral=True
        )


async def setup(client: AutoShardedBot) -> None:
    await client.add_cog(LanguageSettings(client))
