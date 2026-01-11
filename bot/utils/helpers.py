from typing import Callable, Optional, Union

import aiohttp
import json
import re
import aiohttp
import discord
from discord.abc import Messageable
from discord import Message
from discord import File

from typing import Iterable, Optional

from bot.core.bot import Bot
from bot.utils.logger import logger
from bot.utils.settings import settings, ImpersonationProfile
from bot.utils.types import (
    AllowedChannelMixed,
    EmbedAndContentDict,
    EmbedDict,
    EmbedLike,
    RoleLike,
    RolesArg,
)

def get_profile_by_trigger_and_user(
    profile_trigger: str,
    user: discord.abc.Snowflake,
) -> ImpersonationProfile | None:
    """
    Find and return the impersonation profile matching the given trigger
    that the user is allowed to use.

    Args:
        profile_trigger: Trigger string to find the impersonation profile.
        user: The Discord user performing the action (for is_allowed_user checks).  
    Returns:
        The matching ImpersonationProfile, or None if not found.
    """
    return next(
        (p for p in settings.impersonation_profiles
         if profile_trigger.lower() in p.triggers and p.is_allowed_user(user.id)),
        None,
    )


async def send_as_profile(
    profile_trigger: str,
    channel: discord.abc.Messageable,
    content: str,
    *,
    bot: Bot,
    user: discord.abc.Snowflake,
    reply_to: Optional[discord.Message] = None,
    attachments: Optional[Iterable[discord.File]] = None,
    send_callback: Optional[Callable[[str], None]] = None,
    rm_thinking_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """
    Send a message in a channel using the impersonation profile matching the trigger,
    with optional quoting for replies.

    Args:
        profile_trigger: Trigger string to find the impersonation profile.
        channel: Channel or thread to send the message in.
        content: The message content.
        user: The Discord user performing the action (for is_allowed_user checks).
        reply_to: Optional Message to visually reply to.
        attachments: Optional list of discord.File attachments.
        send_callback: Optional async callback for error messages.
        rm_thinking_callback: Optional async callback to remove "thinking..." messages.
        bot: Bot instance for emoji conversion.

    Returns:
        True if the message was sent successfully, False otherwise.
    """

    # --- Check RP enabled ---
    if not is_rp_enabled(channel):
        msg = f"RP is not enabled in this channel ({get_channel_id(channel)})."
        if send_callback:
            await send_callback(msg)
        return False

    # --- Find impersonation profile ---
    profile = get_profile_by_trigger_and_user(profile_trigger, user)

    if not profile:
        profile_listings = [
            f"- **{p.username}**: " + ", ".join(f"`{t}`" for t in p.triggers)
            for p in settings.impersonation_profiles
            if p.is_allowed_user(user.id)
        ]
        msg = (
            f"No impersonation profile found for trigger '{profile_trigger}'.\n\n"
            "Available profiles and triggers:\n" +
            "\n".join(profile_listings)
        )
        if send_callback:
            await send_callback(msg)
        return False

    # --- Ensure channel is valid ---
    if not isinstance(channel, discord.abc.Messageable):
        msg = "Cannot send message in this channel."
        if send_callback:
            await send_callback(msg)
        return False

    try:
        # --- Get or create webhook ---
        webhook = await get_or_create_webhook(channel, profile)

        # --- Format content with quote if replying ---
        async def format_reply(content: str, reply_msg: Optional[discord.Message]) -> tuple[str, list[discord.File]]:
            if reply_msg and not getattr(reply_msg.flags, "ephemeral", False):
                # Include first 200 characters of original content for clarity
                quoted = reply_msg.content.replace("\n", " ")[:200]
                return f"> {reply_msg.author.display_name}: {quoted}\n{content}"
            return await convert_emojis_and_attachments_for_webhook(bot=bot, text=content, attachments={})

        formatted_content, files_to_send = await format_reply(content, reply_to)

        # --- Send message via webhook ---
        await webhook.send(
            formatted_content,
            username=profile.username,
            avatar_url=profile.avatar_url,
            files=attachments if attachments else [] + files_to_send,
        )

        # --- Remove "thinking..." message if needed ---
        if rm_thinking_callback:
            await rm_thinking_callback()

        return True

    except Exception as e:
        msg = f"Failed to send impersonated message: {e}"
        if send_callback:
            await send_callback(msg)
        return False


EMOJI_PATTERN = re.compile(
    r"(?<!<):([a-zA-Z0-9_]+):(?!\d+>)"
)


async def convert_emojis_and_attachments_for_webhook(
    *,
    bot: discord.Client,
    text: str,
    attachments: Optional[Iterable[discord.File]] = None,
    external_emoji_map: Optional[dict[str, str]] = None,
) -> tuple[str, list[discord.File]]:
    """
    Converts :emoji_name: into:
      - <:name:id> or <a:name:id> if the bot has access
      - uploaded image fallback if provided in external_emoji_map

    Returns:
      (converted_text, combined_files)
    """

    files: list[discord.File] = list(attachments or [])

    async def resolve(match: re.Match) -> str:
        name = match.group(1)

        # 1️⃣ Try server emojis the bot can access
        for guild in bot.guilds:
            emoji = discord.utils.get(guild.emojis, name=name)
            if emoji:
                return f"<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>"

        # 2️⃣ External emoji fallback → upload image
        if external_emoji_map and name in external_emoji_map:
            url = external_emoji_map[name]
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        filename = f"{name}.png"
                        files.append(File(fp=data, filename=filename))
                        return f"[{name}]({filename})"

        # 3️⃣ Not found → leave original text
        return match.group(0)

    converted_parts = []
    last_end = 0

    for match in EMOJI_PATTERN.finditer(text):
        converted_parts.append(text[last_end:match.start()])
        converted_parts.append(await resolve(match))
        last_end = match.end()

    converted_parts.append(text[last_end:])

    converted_text = "".join(converted_parts)

    return converted_text, files


async def resolve_message_reference(bot: Bot, reference: discord.MessageReference) -> discord.Message | None:
    """
    Turn a MessageReference into a full Message object.
    Returns None if the message cannot be fetched.
    
    bot: your discord.py bot instance
    reference: the MessageReference object
    """
    if reference is None or reference.message_id is None:
        return None

    # Try to get the channel first
    channel = bot.get_channel(reference.channel_id)
    if channel is None:
        try:
            # fallback: fetch channel from API
            channel = await bot.fetch_channel(reference.channel_id)
        except (discord.NotFound, discord.Forbidden):
            return None

    try:
        # Fetch the actual message
        message = await channel.fetch_message(reference.message_id)
        return message
    except (discord.NotFound, discord.Forbidden):
        return None


async def get_or_create_webhook(channel: discord.TextChannel, profile: "ImpersonationProfile") -> discord.Webhook:
    """
    Fetch an existing webhook for the given impersonation profile in the channel,
    or create one if none exists.

    Args:
        channel (discord.TextChannel): The channel to fetch or create a webhook in.
        profile (ImpersonationProfile): The impersonation profile to use.

    Returns:
        discord.Webhook: The existing or newly created webhook for the profile.
    """
    profile_webhook_name = f"RP: {profile.username}"

    # Fetch all webhooks in the channel
    webhooks = await channel.webhooks()
    for webhook in webhooks:
        # Return webhook if it's owned by the bot and matches the profile's name
        if webhook.user == channel.guild.me and webhook.name == profile_webhook_name:
            #logger.debug(f"Found existing webhook '{webhook.name}' for profile '{profile.username}' in channel {channel.id}.")
            return webhook

    # No matching webhook found, create a new one
    avatar_bytes = None
    if profile.avatar_url:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(profile.avatar_url) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
        except Exception:
            pass  # fallback to no avatar if download fails

    logger.debug(f"Creating new webhook '{profile_webhook_name}' for profile '{profile.username}' in channel {channel.id}.")
    return await channel.create_webhook(
        name=profile_webhook_name,
        avatar=avatar_bytes
    )


def is_rp_enabled(channel: AllowedChannelMixed) -> bool:
    """Check if RP (roleplay) is enabled in the given channel.

    Args:
        channel (AllowedChannelMixed): Channel to check (id, str, or discord channel object).

    Returns:
        bool: True if RP is enabled in the channel, False otherwise.
    """
    return get_channel_id(channel) in settings.enabled_channels


def get_channel_id(channel: AllowedChannelMixed) -> int:
    """Normalize a channel identifier to an integer ID.

    Args:
        channel (AllowedChannelMixed): Channel object, str, or int.

    Returns:
        int: Channel ID.
    """
    if isinstance(channel, str):
        return int(channel)
    if isinstance(channel, int):
        return channel
    return channel.id


def mentions_to_str_list(mentions: list[RoleLike]) -> list[str]:
    """Convert a list of roles or user mentions into strings.

    Args:
        mentions (list[RoleLike]): Roles or mentions.

    Returns:
        list[str]: List of mention strings.
    """
    return [
        m.mention if isinstance(m, (discord.User, discord.Role)) else m
        for m in mentions
    ]


def mentions_to_str(mentions: list[RoleLike]) -> str:
    """Convert a list of roles/users to a single space-separated mention string.

    Args:
        mentions (list[RoleLike]): Roles or mentions.

    Returns:
        str: Space-separated mentions.
    """
    return " ".join(mentions_to_str_list(mentions))


# -------------------------------
# Embed builder utilities
# -------------------------------

def build_discord_embed_with_thumbnail_and_image_and_role_ping(
    title: str = "",
    description: str = "",
    thumbnail_url: str = "",
    image_url: str = "",
    roles: RolesArg = None,
    color: discord.Color = discord.Color.blue(),
) -> EmbedAndContentDict:
    """Build an embed with thumbnail, image, and optional role mentions."""
    role_list: list[RoleLike] = _normalize_roles(roles)
    return build_discord_send_dict_from_embed_like_and_content(
        build_discord_embed_with_thumbnail_and_image(title, description, thumbnail_url, image_url, color),
        mentions_to_str(role_list),
    )


def build_discord_embed_with_thumbnail_and_role_ping(
    title: str = "",
    description: str = "",
    thumbnail_url: str = "",
    roles: RolesArg = None,
    color: discord.Color = discord.Color.blue(),
) -> EmbedAndContentDict:
    """Build an embed with a thumbnail and optional role mentions."""
    role_list: list[RoleLike] = _normalize_roles(roles)
    return build_discord_send_dict_from_embed_like_and_content(
        build_discord_embed_with_thumbnail(title, description, thumbnail_url, color),
        mentions_to_str(role_list),
    )


def build_discord_embed_with_image_and_role_ping(
    title: str = "",
    description: str = "",
    image_url: str = "",
    roles: RolesArg = None,
    color: discord.Color = discord.Color.blue(),
) -> EmbedAndContentDict:
    """Build an embed with an image and optional role mentions."""
    role_list: list[RoleLike] = _normalize_roles(roles)
    return build_discord_send_dict_from_embed_like_and_content(
        build_discord_embed_with_image(title, description, image_url, color),
        mentions_to_str(role_list),
    )


def build_discord_embed_with_role_ping(
    title: str = "",
    description: str = "",
    roles: RolesArg = None,
    color: discord.Color = discord.Color.blue(),
) -> EmbedAndContentDict:
    """Build a simple embed with optional role mentions."""
    role_list: list[RoleLike] = _normalize_roles(roles)
    return build_discord_send_dict_from_embed_like_and_content(
        build_discord_embed(title, description, color),
        mentions_to_str(role_list),
    )


# -------------------------------
# Base embed builders
# -------------------------------

def build_discord_embed_with_thumbnail_and_image(
    title: str = "",
    description: str = "",
    thumbnail_url: str = "",
    image_url: str = "",
    color: discord.Color = discord.Color.blue(),
) -> EmbedDict:
    """Build an embed with thumbnail and image."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    return build_discord_send_dict_from_embed_like_and_content(embed)


def build_discord_embed_with_thumbnail(
    title: str = "",
    description: str = "",
    thumbnail_url: str = "",
    color: discord.Color = discord.Color.blue(),
) -> EmbedDict:
    """Build an embed with a thumbnail only."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return build_discord_send_dict_from_embed_like_and_content(embed)


def build_discord_embed_with_image(
    title: str = "",
    description: str = "",
    image_url: str = "",
    color: discord.Color = discord.Color.blue(),
) -> EmbedDict:
    """Build an embed with an image only."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    if image_url:
        embed.set_image(url=image_url)
    return build_discord_send_dict_from_embed_like_and_content(embed)


def build_discord_embed(
    title: str = "",
    description: str = "",
    color: discord.Color = discord.Color.blue(),
) -> EmbedDict:
    """Build a simple embed with no extra media."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    return build_discord_send_dict_from_embed_like_and_content(embed)


# -------------------------------
# Helper functions
# -------------------------------

def build_discord_send_dict_from_embed_like_and_content(
    embed_like: EmbedLike,
    content: str | None = None,
) -> EmbedDict | EmbedAndContentDict:
    """Convert an embed-like object and optional content to a dict suitable for sending.

    Args:
        embed_like (EmbedLike): A discord.Embed or dict representing an embed.
        content (str | None): Optional message content.

    Returns:
        dict: Dict containing embed and optional content.
    """
    send_args: dict = {}

    if isinstance(embed_like, discord.Embed):
        send_args["embed"] = embed_like
    elif isinstance(embed_like, dict) or isinstance(embed_like, EmbedAndContentDict) or isinstance(embed_like, EmbedDict):
        send_args.update(embed_like)
    else:
        raise TypeError(f"Invalid embed_like argument: {embed_like!r}")

    if content:
        send_args["content"] = content

    return send_args


def _normalize_roles(roles: RolesArg) -> list[RoleLike]:
    """Convert roles argument into a flat list of RoleLike objects.

    Args:
        roles (RolesArg): Single role, list of roles, or None.

    Returns:
        list[RoleLike]: Normalized list of roles.
    """
    if roles is None:
        return []
    if isinstance(roles, (discord.Role, str)):
        return [roles]
    if isinstance(roles, list) or isinstance(roles, tuple):
        return list(roles)
    raise TypeError(f"Invalid roles argument: {roles!r}")
