import discord
from discord import Message
from discord.ext import commands

from bot.core.bot import Bot
from bot.utils.settings import settings
from bot.utils.logger import logger
from bot.utils.helpers import is_rp_enabled, send_as_profile, get_channel_id


# ----------------------------------------------------------------------
# ImpersonationManager Cog
# ----------------------------------------------------------------------

class ImpersonationManager(commands.Cog):
    """Cog responsible for tracking messages in enabled channels."""

    def __init__(self, bot: Bot) -> None:
        """
        Initialize the ImpersonationManager.

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

        # Ignore channels not enabled for RP
        if not is_rp_enabled(message.channel):
            return

        # Define inline callbacks
        async def send_callback(msg: str):
            """Send an ephemeral-style error message in the same channel."""
            logger.warn(f"Failed to send ephemeral error message: {msg}")

        async def rm_thinking():
            """Remove the original 'thinking...' message if present."""
            # In track_messages, nothing special to delete before sending
            pass  # No-op, kept for interface compatibility

        # Expect format: `trigger: message content`
        if not message.content or ":" not in message.content:
            try:
                await message.delete()
                logger.debug(
                    f"Deleted message from {message.author} in {message.channel.id} "
                    "for invalid format (missing colon)."
                )
            except Exception as e:
                logger.warn(f"Failed to delete message: {e}")
            return

        trigger_part, content_part = map(str.strip, message.content.split(":", 1))
        if not trigger_part:
            try:
                await message.delete()
                logger.debug(
                    f"Deleted message from {message.author} in {message.channel.id} "
                    "for empty trigger."
                )
            except Exception as e:
                logger.warn(f"Failed to delete message: {e}")
            return

        # Prepare attachments as discord.File objects
        files: list["discord.File"] = [
            await attachment.to_file() for attachment in message.attachments
        ] if message.attachments else []

        # Send the message via impersonation profile
        success = await send_as_profile(
            profile_trigger=trigger_part,
            channel=message.channel,
            content=content_part,
            attachments=files,
            send_callback=send_callback,
            rm_thinking_callback=rm_thinking,
        )

        # Delete the original message after sending
        try:
            await message.delete()
            if success:
                logger.debug(
                    f"Processed impersonation message from {message.author} "
                    f"in channel {get_channel_id(message.channel)} with trigger '{trigger_part}'"
                )
            else:
                logger.debug(
                    f"Failed to send impersonation message from {message.author} "
                    f"in channel {get_channel_id(message.channel)} with trigger '{trigger_part}'"
                )
        except Exception as e:
            logger.warn(f"Failed to delete message: {e}")
