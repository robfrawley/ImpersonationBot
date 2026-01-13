import discord
from discord.ext import commands

from bot.core.bot import Bot
from bot.db.impersonation_history import impersonation_history
from bot.utils.logger import logger
from bot.utils.settings import settings
from bot.utils.logger import logger
from bot.utils.helpers import is_rp_enabled


REMOVAL_REACTIONS_UNICODE = {"❌", ":x:"}
REMOVAL_REACTIONS_CUSTOM_IDS = {}


class ImpersonationReactedTracker(commands.Cog):
    """Cog responsible for tracking messages reactions to handle user deletions for RP messages they created."""

    def __init__(self, bot: Bot) -> None:
        """
        Initialize the ImpersonationReactedTracker.

        Args:
            bot: Instance of the bot.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent
    ) -> None:
        """ Handle reaction additions to messages in voting channels. """

        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Fetch the channel
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(payload.channel_id)

        # Ignore if channel is not enabled for RP
        if not is_rp_enabled(channel):
            return

        # Get the emoji the user reacted with
        emoji = payload.emoji

        # Check if user is allowed to remove message through reactions (only if they caused the original rp message to be created)
        allowed_user = await impersonation_history.has(payload.user_id, payload.message_id)

        # Check if emoji is one of the allowed ones to invoke this action
        removal_emoji = (
            (emoji.is_unicode_emoji() and emoji.name in REMOVAL_REACTIONS_UNICODE) or
            (emoji.id in REMOVAL_REACTIONS_CUSTOM_IDS)
        )

        # If not a removal emoji, ignore
        if not removal_emoji:
            return

        # Fetch user
        user = payload.member or await self.bot.fetch_user(payload.user_id)

        # Fetch message
        message = await channel.fetch_message(payload.message_id)

        if not allowed_user:
            logger.debug(f'Emoji reaction {emoji} on message {message.id} in channel {channel.id} not allowed for user {user.name}...')
            await message.remove_reaction(payload.emoji, user)
            return

        logger.debug(f'Emoji reaction {emoji} on message {message.id} in channel {channel.id} allowed for user {user.name}, deleting message...')
        await message.delete()
