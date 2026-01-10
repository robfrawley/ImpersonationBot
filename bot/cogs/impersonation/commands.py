import asyncio
import discord
from discord import Interaction
from discord import app_commands
from discord.ext import commands

from typing import Any

from bot.utils.logger import logger
from bot.utils.settings import settings, ImpersonationProfile
from bot.utils.helpers import (
    is_rp_enabled,
    get_channel_id,
    build_discord_embed,
    build_discord_embed_with_thumbnail,
    get_or_create_webhook,
    send_as_profile,
)
from bot.utils.types import AllowedChannel



class ImpersonationCommands(commands.Cog):
    """Cog containing RP (roleplay) system commands."""

    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot

    @app_commands.command(
        name="rp",
        description="Send a message as a configured impersonation profile"
    )
    @app_commands.describe(trigger="Trigger of the impersonation profile", message="Message to send")
    async def rp(
        self,
        interaction: Any,
        trigger: str,
        message: str
    ) -> None:
        """Send a message as the impersonation profile matching the given trigger.

        Args:
            interaction (Interaction): The interaction that triggered the command.
            trigger (str): Trigger of the impersonation profile to use.
            message (str): Message content to send.
        """
        # Defer to handle ephemeral error messages
        await interaction.response.defer(ephemeral=True)

        async def send_callback(msg: str):
            """Send an ephemeral error message to the user."""
            await interaction.followup.send(msg, ephemeral=True)

        async def remove_thinking(msg: str = ""):
            """Delete the original deferred response to remove 'thinking...'."""
            try:
                await interaction.delete_original_response()
            except Exception:
                # ignore if already deleted
                pass

        # Send the impersonated message
        send_success: ImpersonationProfile | bool = await send_as_profile(
            profile_trigger=trigger,
            channel=interaction.channel,
            content=message,
            send_callback=send_callback,
            rm_thinking_callback=remove_thinking,
        )


    @app_commands.command(
        name="rp_status",
        description="Check if the RP system is online",
    )
    @app_commands.describe(channel="Channel to check (defaults to current channel)")
    async def rp_status(
        self,
        interaction: Any,
        channel: AllowedChannel | None = None,
    ):
        """Show whether the RP system is enabled in a channel.

        Args:
            interaction (Interaction): The interaction that triggered the command.
            channel (AllowedChannel | None): Optional channel to check; defaults to the current channel.
        """
        # Defer the interaction with ephemeral response
        await interaction.response.defer(ephemeral=True)

        # Use the provided channel or the current one
        channel = channel or interaction.channel
        channel_id = get_channel_id(channel)
        channel_link = f"<#{channel_id}>"

        # Determine RP status
        enabled = is_rp_enabled(channel_id)
        status_emoji = "✅" if enabled else "❌"
        status_label = "Enabled" if enabled else "Disabled"
        status_log = "ONLINE" if enabled else "OFFLINE"
        thumbnail_url = (
            "https://src.run/get/media/images/dispatch/icon_success-check.png"
            if enabled
            else "https://src.run/get/media/images/dispatch/icon_failure-x.png"
        )

        # Build and send the embed
        await interaction.followup.send(
            **build_discord_embed_with_thumbnail(
                title="Impersonation Status",
                description=(
                    f"Channel: {channel_link}\n"
                    f"Channel ID: `{channel_id}`\n"
                    f"Status: {status_emoji} **{status_label}**"
                ),
                thumbnail_url=thumbnail_url,
            ),
            ephemeral=True,
        )

        # Log the command invocation
        logger.debug(
            f"Impersonation bot status command invoked by "
            f"{interaction.user} in guild/channel "
            f"{interaction.guild.id}/{channel.name} - {status_log}"
        )
