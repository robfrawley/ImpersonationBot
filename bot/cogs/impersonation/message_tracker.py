import re

import discord
from discord import Message
from discord.ext import commands

from bot.core import bot
from bot.utils.webhook_manager import webhook_manager
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

        # Ignore messages from bots
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return

        if isinstance(message.channel, discord.GroupChannel):
            return

        # Ignore channels not enabled for RP
        if not is_rp_enabled(validate_channel(message.channel)):
            return

        await message.delete()

        channel_ident: int = get_channel_id(validate_channel(message.channel))
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

                response: discord.Message = await message.channel.send(
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

            except Exception as e:
                logger.warning(f'Failed to send rp_scene message: {e}')
                await message.channel.send("Failed to send scene message.", delete_after=10)

            return

        # Define inline callbacks
        async def send_callback(msg: str):
            """Send an ephemeral-style error message in the same channel."""
            try:
                await message.channel.send(f'⚠️ {msg}', delete_after=10)
            except Exception as e:
                logger.warning(f'Failed to send ephemeral error message: {e}')

        async def rm_thinking():
            """Remove the original 'thinking...' message if present."""
            # In track_messages, nothing special to delete before sending
            pass  # No-op, kept for interface compatibility

        if not content_found and not message.attachments and not message.stickers:
            # Empty message with no attachments, delete it
            logger.debug(f'Deleted empty message from {message.author} in {channel_ident}: no content or attachments.')
            return

        if not trigger_found:
            default_trigger = await impersonation_default.get(message.author.id)
            if default_trigger:
                trigger_found = default_trigger

        if not trigger_found:
            logger.debug(f'Deleted message from {message.author} in {channel_ident} for invalid format: "{content_found}"')
            return

        # Prepare stickers and attachments
        stickers: list[discord.StickerItem] = message.stickers if message.stickers else []
        files: list["discord.File"] = [
            await attachment.to_file() for attachment in message.attachments
        ] if message.attachments else []

        content_found_parts: list[str] = self._split_message(content_found)

        for part in content_found_parts:
            # Send the message via impersonation profile
            message_sent: discord.Message | None = await send_as_profile(
                bot=self.bot,
                profile_trigger=trigger_found,
                user=message.author,
                channel=message.channel,
                content=part if part else "",
                attachments=files,
                send_callback=send_callback,
                rm_thinking_callback=rm_thinking,
                stickers=stickers if stickers else None,
            )

            if message_sent:
                # Track the impersonated message
                await impersonation_history.add(message.author.id, message_sent.id)

            # Log the result
            try:
                log_msg: str = (
                    f'impersonation message from {message.author} '
                    f'in channel {channel_ident} with trigger "{trigger_found}" (message id: {message_sent.id if message_sent else "N/A"}): "{part}" '
                    f'({len(files)} attachments, {len(stickers) if stickers else 0} stickers, '
                    f'message part {content_found_parts.index(part)+1}/{len(content_found_parts)})'
                )

                if message_sent:
                    logger.debug(f'Processed {log_msg}')
                else:
                    logger.debug(f'Failed to send {log_msg}')

            except Exception as e:
                logger.warning(f'Failed to delete message: {e}')

            # Unset stickers and attachments after the first part
            stickers = []
            files = []

    def _split_message(self, message: str, limit: int = 2000) -> list[str]:
        """
        Split a message into chunks not exceeding the specified character limit.

        Args:
            message: The message to split.
            limit: The maximum number of characters per chunk.

        Returns:
            A list of message chunks.
        """
        if len(message) <= limit:
            return [message]

        chunks: list[str] = []
        current_chunk: str = ""

        for line in message.splitlines(keepends=True):
            if len(current_chunk) + len(line) > limit:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                if len(line) > limit:
                    for i in range(0, len(line), limit):
                        chunks.append(line[i:i + limit])
                else:
                    current_chunk = line
            else:
                current_chunk += line

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
