import io
import re
from typing import Callable, Iterable, Awaitable

import aiohttp
import discord
from discord import File

from bot.core.bot import Bot
from bot.utils.logger import logger
from bot.utils.settings import ImpersonationProfile, settings
from bot.utils.webhook_manager import webhook_manager
from bot.utils.types import (
    AllowedChannelMixed,
    AllowedChannelMixedOrNone,
    EmbedAndContentDict,
    EmbedDict,
    EmbedDictWithOptionalContent,
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
    reply_to: discord.Message | None = None,
    attachments: Iterable[discord.File] | None = None,
    stickers: Iterable[discord.StickerItem] | None = None,
    send_callback: Callable[[str], Awaitable[None]] | None = None,
    rm_thinking_callback: Callable[[], Awaitable[None]] | None = None,
) -> discord.Message | None:
    """
    Send a message via webhook impersonation.

    Returns:
        The new webhook message ID if sent successfully, otherwise None.
    """

    if not isinstance(channel, discord.TextChannel):
        raise ValueError("Only TextChannel is supported for impersonation.")

    if not is_rp_enabled(channel):
        msg = f"RP is not enabled in this channel ({get_channel_id(channel)}). Invoked by {user}."
        if send_callback:
            await send_callback(msg)
        return None

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
        return None

    if not isinstance(channel, discord.TextChannel):
        if send_callback:
            await send_callback(f"Cannot send message in this channel. Invoked by {user}.")
        return None

    #print('### webhook_manager[before]:', webhook_manager)
    #print(f'### webhook_manager.webhooks({len(webhook_manager.webhooks)}:{len(webhook_manager.webhooks[channel.id]) if channel.id in webhook_manager.webhooks else 0}):[before]', webhook_manager.webhooks)
    #new_p = await webhook_manager.get_for_profile(profile, channel)
    #print('### new_p:', new_p)
    #print('### webhook_manager[after]:', webhook_manager)
    #print(f'### webhook_manager.webhooks({len(webhook_manager.webhooks)}:{len(webhook_manager.webhooks[channel.id]) if channel.id in webhook_manager.webhooks else 0}):[after]', webhook_manager.webhooks)

    try:
        webhook = await get_or_create_webhook(channel, profile)

        async def format_reply(
            content: str,
            reply_msg: discord.Message | None
        ) -> tuple[str, list[discord.File]]:
            if reply_msg and not getattr(reply_msg.flags, "ephemeral", False):
                quoted = reply_msg.content.replace("\n", " ")[:200]
                return (
                    f"> {reply_msg.author.display_name}: {quoted}\n{content}",
                    []
                )
            return await convert_emojis_and_attachments_for_webhook(
                bot=bot,
                text=content,
                attachments={}
            )

        formatted_content, files_to_send = await format_reply(content, reply_to)

        for sticker in stickers or []:
            try:
                sticker_file = await fetch_sticker_as_file_safe(
                    sticker,
                    guild=getattr(channel, "guild", None)
                )
                files_to_send.append(sticker_file) if sticker_file else None
            except Exception as e:
                logger.warning(f'Failed to fetch sticker {sticker.name}: {e}')

        message: discord.Message = await webhook.send(
            formatted_content,
            username=profile.username,
            avatar_url=profile.avatar_url,
            files=(list(attachments) if attachments else []) + files_to_send,
            wait=True,
        )

        if rm_thinking_callback:
            await rm_thinking_callback()

        return message

    except Exception as e:
        if send_callback:
            await send_callback(f"Failed to send impersonated message: {e}")
        return None


async def fetch_sticker_as_file_safe(sticker, guild=None):
    """
    Returns a discord.File for a sticker if possible.
    - Converts Lottie guild stickers to GIF.
    - Uses CDN URL for static external stickers.
    - Skips animated external stickers (cannot convert).
    """
    # Try to fetch full Sticker if in a guild
    if guild:
        try:
            sticker = await guild.fetch_sticker(sticker.id)
        except Exception:
            pass  # external/global sticker

    # Static stickers (PNG/APNG)
    if getattr(sticker, "format_type", 1) in {1, 3}:
        # Use URL if possible, fallback to CDN
        url = getattr(sticker, "url", f"https://cdn.discordapp.com/stickers/{sticker.id}.png")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        return File(io.BytesIO(data), filename=f"{sticker.name}.png")

    # Lottie stickers (only guild stickers supported)
    if getattr(sticker, "format_type", 0) == 2:
        if hasattr(sticker, "url"):
            async with aiohttp.ClientSession() as session:
                async with session.get(sticker.url) as resp:
                    data = await resp.read()
            from lottie import importers, exporters
            animation = importers.from_bytes(data) # type: ignore
            gif_bytes = exporters.to_bytes(animation, format="gif") # type: ignore
            return File(io.BytesIO(gif_bytes), filename=f"{sticker.name}.gif")
        else:
            logger.warning(f'Sticker {sticker.name} has no URL to fetch Lottie data.')
            return None

EMOJI_PATTERN = re.compile(
    r"(?<!<):([a-zA-Z0-9_]+):(?!\d+>)"
)

async def convert_emojis_and_attachments_for_webhook(
    *,
    bot: discord.Client,
    text: str,
    attachments: Iterable[discord.File] | None = None,
    external_emoji_map: dict[str, str] | None = None,
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


async def get_or_create_webhook(channel: discord.TextChannel, profile: ImpersonationProfile) -> discord.Webhook:
    """
    Fetch an existing webhook for the given impersonation profile in the channel,
    or create one if none exists.

    Args:
        channel (discord.TextChannel): The channel to fetch or create a webhook in.
        profile (ImpersonationProfile): The impersonation profile to use.

    Returns:
        discord.Webhook: The existing or newly created webhook for the profile.
    """
    return await webhook_manager.get_for_profile(profile, channel)

    profile_webhook_name = f"RP:{profile.username}"

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

def validate_channel(channel: discord.abc.Messageable) -> discord.TextChannel:
    """Normalize a channel identifier to a discord.TextChannel object.

    Args:
        channel (AllowedChannelMixed): Channel to normalize (id, str, or discord channel object).

    Returns:
        discord.TextChannel: The normalized TextChannel object.

    Raises:
        ValueError: If the channel cannot be found or is of an unsupported type.
    """
    if isinstance(channel, discord.TextChannel):
        return channel
    else:
        raise ValueError(f"Unsupported channel type: {type(channel)}")


def is_rp_enabled(channel: AllowedChannelMixedOrNone) -> bool:
    """Check if RP (roleplay) is enabled in the given channel.

    Args:
        channel (AllowedChannelMixed): Channel to check (id, str, or discord channel object).

    Returns:
        bool: True if RP is enabled in the channel, False otherwise.
    """
    return get_channel_id(channel) in settings.enabled_channels


def get_channel_id(channel: AllowedChannelMixedOrNone) -> int:
    """Normalize a channel identifier to an integer ID.

    Args:
        channel (AllowedChannelMixedOrNone): Channel object, str, int, or None.
    Returns:
        int: Channel ID.
    """

    if channel is None:
        raise ValueError("Channel cannot be None.")

    if isinstance(channel, str):
        return int(channel)

    elif isinstance(channel, int):
        return channel

    elif isinstance(channel, (discord.TextChannel, discord.Thread)):
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
) -> EmbedDictWithOptionalContent:
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
    timestamp: discord.datetime | None = discord.utils.utcnow(),
) -> EmbedDictWithOptionalContent:
    """Build a simple embed with no extra media."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=timestamp,
    )
    return build_discord_send_dict_from_embed_like_and_content(embed)


# -------------------------------
# Helper functions
# -------------------------------

def build_discord_send_dict_from_embed_like_and_content(
    embed_like: EmbedLike,
    content: str | None = None,
):
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

    if content is not None:
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
