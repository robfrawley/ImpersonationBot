import re

import discord
from discord import Message
from discord.ext import commands

from bot.db.impersonation_default import impersonation_default
from bot.db.impersonation_history import impersonation_history
from bot.core.bot import Bot
from bot.utils.logger import logger
from bot.utils.helpers import (
    is_rp_enabled,
    validate_channel,
    send_as_profile,
    get_channel_id,
    build_discord_embed,
)


# ----------------------------------------------------------------------
# ImpersonationMessageTracker Cog
# ----------------------------------------------------------------------

class ImpersonationMessageTracker(commands.Cog):
    """Cog responsible for tracking messages in enabled channels."""

    def __init__(self, bot: Bot) -> None:
        """
        Initialize the ImpersonationMessageTracker.

        Args:
            bot: Instance of the bot.
        """
        self.bot = bot

    async def track_messages(self, message: Message) -> None:
        """
        Listen for messages in enabled channels and impersonate profiles
        if the message starts with a known trigger.

        This supports both text and attachments. Messages not following
        the `trigger: message` format will be deleted.
        """

        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return

        if isinstance(message.channel, discord.GroupChannel):
            return

        channel: discord.TextChannel = validate_channel(message.channel)

        async def send_callback(msg: str):
            try:
                await channel.send(f'⚠️ {msg}', delete_after=10)
            except Exception as e:
                logger.warning(f'Failed to send callback message ("{msg}"): {e}')

        async def rm_thinking():
            pass

        if not is_rp_enabled(channel):
            return

        channel_ident: int = get_channel_id(channel)
        content_origs: str = message.content.strip() if message.content else ""
        trigger_match: re.Match | None = re.fullmatch(r'\s*([a-z0-9-_]+?)\s*:(.*)', content_origs, re.IGNORECASE | re.DOTALL)
        trigger_found: str | None = trigger_match.group(1).strip() if trigger_match else None
        content_found: str = trigger_match.group(2).strip() if trigger_match else content_origs

        if trigger_found and trigger_found.startswith('http'):
            trigger_found = None
            content_found = content_origs

        if trigger_found == 'scene' and content_found:
            content_found = content_found.upper()
            try:
                logger.debug(f'Sending scene message from "{message.author}" in "{channel_ident}": "{content_found}"')

                response: discord.Message = await channel.send(
                    **build_discord_embed(
                        description=(
                            f'```\n'
                            f'{content_found}\n'
                            f'```'
                        ),
                        timestamp=None,
                        color=discord.Color.blue(),
                    )
                )

                if response:
                    await impersonation_history.add(message.author.id, response.id)

                await self._delete_message(message)

            except Exception as e:
                logger.warning(f'Failed to send scene message: {e}')
                await channel.send("Failed to send scene message.", delete_after=10)

            return

        if not content_found and not message.attachments and not message.stickers:
            # Empty message with no attachments or stickers, delete it
            logger.debug(f'Deleted empty message from "{message.author}" in "{channel_ident}": no content or attachments.')
            await self._delete_message(message)
            return

        if not trigger_found:
            default_trigger = await impersonation_default.get(message.author.id)
            if default_trigger:
                trigger_found = default_trigger

        if not trigger_found:
            logger.debug(f'Deleted message from "{message.author}" in "{channel_ident}" for invalid format: "{content_found}"')
            await self._delete_message(message)
            return

        # Prepare stickers and attachments
        stkrs: list[discord.StickerItem] = list(message.stickers) if message.stickers else []
        files: list[discord.File] = [
            await attachment.to_file() for attachment in message.attachments
        ] if message.attachments else []

        # Split content into parts if necessary
        content_file_only: bool = not content_found and (bool(files) or bool(stkrs))
        content_parts_msg: list[str] = [""] if content_file_only else self._split_message(content_found)
        content_parts_len: int = len(content_parts_msg)

        for i, part in enumerate(content_parts_msg):
            content_part_last: bool = (i == content_parts_len - 1)
            content_part_files: list[discord.File] = files if content_part_last else []
            content_part_stkrs: list[discord.StickerItem] = stkrs if content_part_last else []

            message_sent: discord.Message | None = await send_as_profile(
                bot=self.bot,
                profile_trigger=trigger_found,
                user=message.author,
                channel=channel,
                content=part or "",
                attachments=content_part_files or None,
                stickers=content_part_stkrs or None,
                send_callback=send_callback,
                rm_thinking_callback=rm_thinking,
            )

            if message_sent:
                await impersonation_history.add(message.author.id, message_sent.id)

            # Log the result
            log_msg: str = (
                f"impersonation message \"{message_sent.id if message_sent else 'N/A'}\" from \"{message.author}\" "
                f'in channel "{channel_ident}" using "{trigger_found}" trigger: '
                f'"{part if part else "<empty-message-string>"}" '
                f'('
                f'{len(content_part_files)}/{len(files)} attachments, '
                f'{len(content_part_stkrs)}/{len(stkrs)} stickers, '
                f'{i+1}/{content_parts_len} message parts'
                f')'
            )
            logger.debug(f'Processed {log_msg}' if message_sent else f'Failed to send {log_msg}')

        await self._delete_message(message)

    async def _delete_message(self, message: Message) -> None:
        """
        Delete a message from a channel.

        Args:
            message: The message to delete.
        """
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f'Failed to delete message "{message.id}": {e}')

    def _split_message(self, message: str, limit: int = 1999) -> list[str]:
        """
        Split a message into parts not exceeding the specified character limit.

        Args:
            message: The message to split.
            limit: The maximum number of characters per chunk.

        Returns:
            A list of message parts.
        """
        if len(message) <= limit:
            return [message]

        parts: list[str] = []
        chunk: str = ""

        for line in message.splitlines(keepends=True):
            if len(chunk) + len(line) > limit:
                if chunk:
                    parts.append(chunk)
                    chunk = ""
                if len(line) > limit:
                    for i in range(0, len(line), limit):
                        parts.append(line[i:i + limit])
                else:
                    chunk = line
            else:
                chunk += line

        if chunk:
            parts.append(chunk)

        return parts
