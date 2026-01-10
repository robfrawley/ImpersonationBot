import discord
from collections.abc import Iterable

# ----------------------------------------------------------------------
# Type aliases for channels, embeds, and roles
# ----------------------------------------------------------------------

# Channels that the bot can interact with
AllowedChannel = discord.TextChannel | discord.Thread
AllowedChannelMixed = AllowedChannel | int | str  # Can also be ID or name

# Embed-related types
class EmbedAndContentDict(dict):
    """Dictionary containing an embed and optional content for sending messages."""
    embed: discord.Embed
    content: str

class EmbedDict(dict):
    """Dictionary containing only an embed."""
    embed: discord.Embed

# Union type for any object that can be sent as a Discord embed
EmbedLike = discord.Embed | EmbedDict | EmbedAndContentDict

# Role types
RoleLike = discord.Role | str  # Either a Role object or role mention string
RolesArg = RoleLike | Iterable[RoleLike] | None  # Single role, multiple roles, or None
