from discord.app_commands import checks

#                       THIS FILE INCLUDES SOME PERMISSION SETS FOR MOST THINGS IN THIS PROJECT.
#                               To avoid changing these values everywhere in the project,
#                  we store them here to easily adjust it later and to use it as a guide for what is possible.

perms_send_message = checks.has_permissions(
    send_messages=True,
    send_messages_in_threads=True,
    external_emojis=True,
    external_stickers=True,
    embed_links=True,
    read_message_history=True,
    attach_files=True,
    view_channel=True,
)
"""Command check ensuring the context/author has standard message delivery permissions."""
