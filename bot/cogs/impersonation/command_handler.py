import asyncio
import discord
from discord import Interaction
from discord import app_commands
from discord.ext import commands

from typing import Any

from bot.core.bot import user_config
from bot.utils.logger import logger
from bot.utils.settings import settings, ImpersonationProfile
from bot.utils.helpers import (
    is_rp_enabled,
    get_channel_id,
    build_discord_embed,
    build_discord_embed_with_thumbnail,
    get_or_create_webhook,
    send_as_profile,
    get_profile_by_trigger_and_user,
)
from bot.utils.types import AllowedChannel


class ImpersonationCommandHandler(commands.Cog):
    """Cog containing RP (roleplay) system commands."""

    def __init__(self, bot: commands.Bot):
        """
        Initialize the cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot

    async def trigger_autocomplete(self, interaction: Interaction, current: str):
        """Autocomplete first triggers, showing user's current default at the top."""
        choices = []

        # Get user's current default trigger
        user_id = interaction.user.id
        current_default = await user_config.get_default_trigger(user_id)

        # Add first trigger of each profile
        for profile in settings.impersonation_profiles:
            if not profile.triggers or not profile.is_allowed_user(interaction.user.id):
                continue

            first_trigger = profile.triggers[0]

            if current.lower() in first_trigger.lower():
                description = f"{profile.username} ({', '.join(profile.triggers)})"

                if current_default in profile.triggers:
                    description += " [CURRENT DEFAULT]"

                choices.append(app_commands.Choice(
                    name=description,
                    value=first_trigger
                ))

            if len(choices) >= 25:  # Discord limit
                break

        return choices

    @app_commands.command(
        name="rp",
        description="Send a message as a configured impersonation profile"
    )
    @app_commands.describe(
        trigger="Trigger of the impersonation profile",
        message="Message to send"
    )
    @app_commands.autocomplete(trigger=trigger_autocomplete)
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
            bot=self.bot,
            profile_trigger=trigger,
            user=interaction.user,
            channel=interaction.channel,
            content=message,
            send_callback=send_callback,
            rm_thinking_callback=remove_thinking,
        )

    @app_commands.command(
        name="rp_default",
        description="Set or unset a default profile for your RP messages"
    )
    @app_commands.describe(
        trigger="The trigger of the impersonation profile to set as default. Leave empty to unset."
    )
    @app_commands.autocomplete(trigger=trigger_autocomplete)
    async def rp_default(self, interaction: Interaction, trigger: str | None = None):
        """Set or unset a default profile for your RP messages."""
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        if not trigger or trigger.strip() == "":
            # Unset default
            await user_config.unset_default_trigger(user_id)
            await interaction.followup.send(
                **build_discord_embed(
                    title="✅ Default RP Profile Unset",
                    description="Your default RP profile has been unset."
                ),
                ephemeral=True
            )
        else:
            # Set default
            await user_config.set_default_trigger(user_id, trigger.strip())
            profile: ImpersonationProfile | None = get_profile_by_trigger_and_user(trigger.strip(), interaction.user)

            if not profile:
                await interaction.followup.send(
                    **build_discord_embed(
                        title="⚠️ Default RP Profile Warning",
                        description=(
                            f"The trigger `{trigger.strip()}` does not match any available profile. "
                            f"You may not be able to use it until a matching profile is added.",
                        )
                    ),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    **build_discord_embed_with_thumbnail(
                        title="✅ Default RP Profile Set",
                        description=(
                            f"Your default RP profile has been set to **{profile.username}** "
                            f"(`{trigger.strip()}`).\n\n"
                            f"You can now send messages normally in chat without specifying a trigger, "
                            f"though you can still specify a different trigger if desired."
                        ),
                        thumbnail_url=profile.bust_url if profile.bust_url else profile.avatar_url,
                    ),
                    ephemeral=True,
                )

    @app_commands.command(
        name="rp_help",
        description="Show help about using the RP system",
    )
    async def rp_help(
        self,
        interaction: Any
    ):
        """Show help about using the RP system.

        Args:
            interaction (Interaction): The interaction that triggered the command.
            channel (AllowedChannel | None): Optional channel to check; defaults to the current channel.
        """
        # Defer the interaction with ephemeral response
        await interaction.response.defer(ephemeral=True)

        async def send_callback(msg: str):
            """Send an ephemeral error message to the user."""
            await interaction.followup.send(msg, ephemeral=True)

        # Check if RP is enabled in this channel
        if not is_rp_enabled(interaction.channel):
            msg = f"RP is not enabled in this channel ({get_channel_id(interaction.channel)})."
            if send_callback:
                await send_callback(msg)
            logger.warn(msg)
            return False

        profile_listings = [
            f"- **{p.username}**: " + ", ".join(f"`{t}`" for t in p.triggers)
            for p in settings.impersonation_profiles
            if p.is_allowed_user(interaction.user.id)
        ]
        msg = (
            f"Available profiles and triggers:\n" +
            "\n".join(profile_listings)
        )
        if send_callback:
            await send_callback(msg)

        return False



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
