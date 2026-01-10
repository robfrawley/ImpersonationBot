from typing import Callable, Optional, Union

import discord
from discord.abc import Messageable

from bot.utils.logger import logger
from bot.utils.settings import settings
from bot.utils.types import (
    AllowedChannelMixed,
    EmbedAndContentDict,
    EmbedDict,
    EmbedLike,
    RoleLike,
    RolesArg,
)


async def send_as_profile(
    profile_trigger: str,
    channel: Messageable,
    content: str,
    *,
    attachments: Optional[list["discord.File"]] = None,
    send_callback: Optional[Callable[[str], None]] = None,
    rm_thinking_callback: Optional[Callable[[], None]] = None,
) -> bool:
    """Send a message in a channel using the impersonation profile matching the trigger.

    Args:
        profile_trigger (str): Trigger string to find the impersonation profile.
        channel (Messageable): The Discord channel or thread to send the message in.
        content (str): The message content to send.
        attachments (Optional[list["discord.File"]]): Optional attachments to include.
        send_callback (Optional[Callable[[str], None]]): Optional async callback
            for sending ephemeral-style error messages (e.g., in slash commands).
        rm_thinking_callback (Optional[Callable[[], None]]): Optional async callback
            to remove the original "thinking..." response.

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    # Check if RP is enabled in this channel
    if not is_rp_enabled(channel):
        msg = f"RP is not enabled in this channel ({get_channel_id(channel)})."
        if send_callback:
            await send_callback(msg)
        logger.warn(msg)
        return False

    # Find the profile by trigger
    profile = next(
        (p for p in settings.impersonation_profiles if profile_trigger in p.triggers),
        None,
    )
    if not profile:
        profile_listings = [
            f"- **{p.username}**: " + ", ".join(f"`{t}`" for t in p.triggers)
            for p in settings.impersonation_profiles
        ]
        msg = (
            f"No impersonation profile found for trigger '{profile_trigger}'.\n\n"
            "Available profiles and triggers:\n" +
            "\n".join(profile_listings)
        )
        if send_callback:
            await send_callback(msg)
        logger.warn(f"No impersonation profile found for trigger '{profile_trigger}'.")
        return False

    if not isinstance(channel, Messageable):
        msg = "Cannot send message in this channel."
        if send_callback:
            await send_callback(msg)
        logger.warn(msg)
        return False

    try:
        webhook = await get_or_create_webhook(channel)
        await webhook.send(
            content,
            username=profile.username,
            avatar_url=profile.avatar_url,
            files=attachments if attachments else []
        )
        logger.info(f"Sent message as {profile.username} in channel {get_channel_id(channel)}")

        # Remove the "thinking..." message if callback is provided
        if rm_thinking_callback:
            await rm_thinking_callback()

        return True
    except Exception as e:
        msg = f"Failed to send impersonated message: {e}"
        if send_callback:
            await send_callback(msg)
        logger.warn(msg)
        return False


async def get_or_create_webhook(channel: discord.TextChannel) -> discord.Webhook:
    """Fetch an existing webhook for the bot in the channel or create one if none exists.

    Args:
        channel (discord.TextChannel): The channel to fetch or create a webhook in.

    Returns:
        discord.Webhook: The existing or newly created webhook.
    """
    webhooks = await channel.webhooks()
    for webhook in webhooks:
        # Return the webhook owned by the bot
        if webhook.user == channel.guild.me:
            return webhook

    # No webhook exists, create one
    return await channel.create_webhook(name="Impersonator")


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
