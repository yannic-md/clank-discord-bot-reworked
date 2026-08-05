import logging
import traceback
import uuid
from logging import Logger
from pathlib import Path

import discord
from discord import Forbidden, Guild, Interaction
from discord.app_commands import AppCommandError
from discord.app_commands.errors import BotMissingPermissions, MissingPermissions
from discord.ext.commands import Context
from discord.ext.commands.errors import BotMissingPermissions as CommandBotMissingPermissions
from discord.ext.commands.errors import CommandError, CommandNotFound
from discord.ext.commands.errors import MissingPermissions as CommandMissingPermissions

from core.discord_api.limits import MAX_MESSAGE_CONTENT
from core.enums.language import DEFAULT_LANGUAGE, SupportedLanguage
from core.i18n.resolve import get_language
from core.i18n.translator import lookup, translate
from core.setup.dotenv import ERROR_LOG_ID, HOME_GUILD_ID
from core.setup.logger import LOG_DIR

logger: Logger = logging.getLogger("discord")
_HANDLED_ATTR: str = "_ccd_handled"
_IGNORED_COMMAND_ERRORS: tuple[type[CommandError], ...] = (CommandNotFound,)

ERROR_DUMP_DIR: Path = LOG_DIR / "errors"


def _unwrap(error: BaseException) -> BaseException:
    """Return the original exception a discord.py wrapper error chained via `raise ... from e`, or `error` itself."""
    return error.__cause__ if error.__cause__ is not None else error


def _translate_permission(language: SupportedLanguage, perm: str) -> str:
    """Translate a discord.py permission flag name (e.g. "manage_roles") into its display name."""
    key: str = f"errors.permissions.{perm}"
    fallback: str = perm.replace("_", " ").replace("guild", "server").title()
    return lookup(language, key) or lookup(DEFAULT_LANGUAGE, key) or fallback


def _format_permissions(language: SupportedLanguage, missing: list[str]) -> str:
    """Turn discord.py permission flag names into a human-readable, translated, comma-separated list."""
    return ", ".join(_translate_permission(language, perm).upper() for perm in missing)


async def _notify_error_channel(client: discord.Client, command_name: str, original: BaseException) -> None:
    """Forward an unexpected error's traceback to the configured error-log channel, if one is configured.

    Args:
        client (discord.Client): The bot instance, used to resolve the guild/channel.
        command_name (str): Name of the command that raised the error, for context.
        original (BaseException): The unwrapped exception to report.
    """
    if HOME_GUILD_ID == "0" or ERROR_LOG_ID == "0":
        return

    home_guild: Guild | None = client.get_guild(int(HOME_GUILD_ID))
    if home_guild is None:
        return

    error_channel = home_guild.get_channel_or_thread(int(ERROR_LOG_ID))
    if not isinstance(error_channel, discord.abc.Messageable):
        return

    traceback_text: str = "".join(traceback.format_exception(type(original), original, original.__traceback__))
    content: str = f"```py\nCOMMAND ERROR (/{command_name}):\n\n{traceback_text}\n```"

    try:
        if len(content) <= MAX_MESSAGE_CONTENT:
            await error_channel.send(content=content)
            return

        ERROR_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        dump_path = ERROR_DUMP_DIR / f"error_{uuid.uuid4().hex}.txt"
        dump_path.write_text(traceback_text, encoding="utf-8")

        await error_channel.send(content=f"```py\nCOMMAND ERROR (/{command_name}):\n\nToo long, saved to {dump_path}\n```")
    except discord.HTTPException:
        logger.warning("Could not forward error notification to the error-log channel for command '%s'", command_name)


async def _reply_to_interaction(interaction: Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        # The interaction likely expired or was already acknowledged elsewhere; nothing more we can do.
        logger.warning("Could not deliver error reply for interaction %s", interaction.id)


def _permission_error(original: BaseException) -> tuple[str, list[str]] | None:
    """Resolve (translation key, missing permission names) for a missing-permissions error, or `None` if it isn't one."""
    if isinstance(original, BotMissingPermissions | CommandBotMissingPermissions):
        return "errors.no_permission.bot", original.missing_permissions
    if isinstance(original, MissingPermissions | CommandMissingPermissions):
        return "errors.no_permission.user", original.missing_permissions
    return None


async def error_handler(interaction: Interaction, error: AppCommandError) -> None:
    """Global handler for app command (slash command / interaction) errors.

    Args:
        interaction (Interaction): The interaction that raised the error.
        error (AppCommandError): The error raised by the command tree.
    """
    if getattr(error, _HANDLED_ATTR, False):
        return

    command_name: str = interaction.command.qualified_name if interaction.command is not None else "<unknown command>"
    original: BaseException = _unwrap(error)

    # fallback for bot-permission related issues
    if isinstance(original, Forbidden):
        message: str = translate(await get_language(interaction), "errors.no_permission.fallback")
        await _reply_to_interaction(interaction, message)
        return

    permission_error: tuple[str, list[str]] | None = _permission_error(original)
    if permission_error is not None:
        key, missing_permissions = permission_error
        language = await get_language(interaction)
        message = translate(language, key, permissions=_format_permissions(language, missing_permissions))
        await _reply_to_interaction(interaction, message)
        return

    logger.error("Unhandled error in app command '%s'", command_name, exc_info=original)
    message = translate(await get_language(interaction), "errors.unexpected")
    await _reply_to_interaction(interaction, message)
    await _notify_error_channel(interaction.client, command_name, original)


async def command_error_handler(_ctx: Context, error: CommandError) -> None:
    """Global handler for classic prefix-command errors.

    Because prefix commands are not supported anymore, we just ignore the default library errors.

    Args:
        _ctx (Context): The invocation context of the failed command.
        error (CommandError): The error raised while parsing/invoking the command.
    """
    if isinstance(error, _IGNORED_COMMAND_ERRORS):
        return
