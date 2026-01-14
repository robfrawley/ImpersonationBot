import discord
from discord import Interaction
from discord import app_commands
from discord.ext import commands

from collections.abc import Callable
from typing import Any

from bot.core.bot import Bot
from bot.db.impersonation_default import impersonation_default
from bot.db.impersonation_history import impersonation_history
from bot.utils.logger import logger
from bot.utils.settings import settings, ImpersonationProfile
from bot.utils.helpers import (
    is_rp_enabled,
    get_channel_id,
    build_discord_embed,
    build_discord_embed_with_thumbnail,
    build_discord_embed_with_thumbnail_and_image,
    send_as_profile,
    get_profile_by_trigger_and_user,
)
from bot.utils.types import AllowedChannel


class ImpersonationCommandHandler(commands.Cog):
    """Cog containing RP (roleplay) system commands."""

    def __init__(self, bot: Bot):
        """
        Initialize the cog.

        Args:
            bot (Bot): The bot instance.
        """
        self.bot = bot

    async def _autocomplete_trigger(self, interaction: Interaction, current: str):
        """Autocomplete first triggers, showing user's current default at the top."""
        choices = []

        # Get user's current default trigger
        user_id = interaction.user.id
        current_default = await impersonation_default.get(user_id)

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
    @app_commands.autocomplete(trigger=_autocomplete_trigger)
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

        async def send_callback(msg: str) -> None:
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
        message_sent: discord.Message | None = await send_as_profile(
            bot=self.bot,
            profile_trigger=trigger,
            user=interaction.user,
            channel=interaction.channel,
            content=message,
            send_callback=send_callback,
            rm_thinking_callback=remove_thinking,
        )

        if message_sent:
            # Track the impersonated message
            await impersonation_history.add(interaction.user.id, message_sent.id)

    async def _autocomplete_scene_location(
        self,
        interaction: Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for scene location type."""
        options: dict[str, str] = {
            "INT.": "Interior",
            "EXT.": "Exterior",
            "INT./EXT.": "Interior/Exterior"
        }

        return [
            app_commands.Choice(name=f"{description} ({option})", value=option)
            for option, description in options.items()
            if current.lower() in option.lower() or current.lower() in description.lower()
        ][:25]

    async def _autocomplete_scene_time_of_day(
        self,
        interaction: Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for scene time of day."""
        options: dict[str, str] = {
            "DAY": "Daytime",
            "NIGHT": "Nighttime",
            "DAWN": "Dawn",
            "DUSK": "Dusk",
            "MORNING": "Morning",
            "AFTERNOON": "Afternoon",
            "EVENING": "Evening"
        }

        return [
            app_commands.Choice(name=f"{description} ({option})", value=option)
            for option, description in options.items()
            if current.lower() in option.lower() or current.lower() in description.lower()
        ][:25]

    async def _autocomplete_scene_color(
        self,
        interaction: Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for scene embed color."""

        options: dict[str, discord.Color] = {
            "Teal (#1ABC9C)": discord.Color.teal(),
            "Dark Teal (#11806A)": discord.Color.dark_teal(),
            "Green (#2ECC71)": discord.Color.green(),
            "Dark Green (#1F8B4C)": discord.Color.dark_green(),
            "Blue (#3498DB)": discord.Color.blue(),
            "Dark Blue (#206694)": discord.Color.dark_blue(),
            "Purple (#9B59B6)": discord.Color.purple(),
            "Dark Purple (#71368A)": discord.Color.dark_purple(),
            "Magenta (#E91E63)": discord.Color.magenta(),
            "Dark Magenta (#AD1457)": discord.Color.dark_magenta(),
            "Gold (#F1C40F)": discord.Color.gold(),
            "Dark Gold (#C27C0E)": discord.Color.dark_gold(),
            "Orange (#E67E22)": discord.Color.orange(),
            "Dark Orange (#A84300)": discord.Color.dark_orange(),
            "Red (#E74C3C)": discord.Color.red(),
            "Dark Red (#992D22)": discord.Color.dark_red(),
            "Fuchsia (#EB459E)": discord.Color.fuchsia(),
            "Yellow (#FEE75C)": discord.Color.yellow(),
            "Pink (#EB459F)": discord.Color.pink(),
            "White (#FFFFFF)": discord.Color.light_embed(),
            "Lightest Grey (#95A5A6)": discord.Color.lighter_grey(),
            "Light Grey (#979C9F)": discord.Color.light_grey(),
            "Dark Grey (#607d8b)": discord.Color.dark_grey(),
            "Darkest Grey (#546E7A)": discord.Color.darker_grey(),
            "Random": discord.Color.random(),
        }

        return [
            app_commands.Choice(name=name, value=hex(color.value))
            for name, color in options.items()
            if current.lower() in name.lower()
        ][:25]

    @app_commands.command(
        name="rp_scene",
        description="Outputs a scene-setting message"
    )
    @app_commands.describe(
        setting="The location of the scene",
        location="Type of location (e.g., INT., EXT., INT./EXT.)",
        time_of_day="Time of day for the scene",
        parenthetical="Additional parenthetical information for the scene",
        color="Color for the embed"
    )
    @app_commands.autocomplete(
        location=_autocomplete_scene_location,
        time_of_day=_autocomplete_scene_time_of_day,
        color=_autocomplete_scene_color
    )
    async def rp_scene(
        self,
        interaction: Any,
        setting: str,
        time_of_day: str | None = None,
        location: str | None = None,
        parenthetical: str | None = None,
        color: str | None = None,
    ) -> None:
        """Outputs a scene-setting message.

        Args:
            interaction (Interaction): The interaction that triggered the command.
            setting (str): The name of the location for the scene.
            time_of_day (str | None): The time of day for the scene.
            location (str | None): The type of location (e.g., INT., EXT., INT./EXT.).
            parenthetical (str | None): Additional parenthetical information for the scene.
            color (str | None): The color for the embed.
        """
        # Defer to handle ephemeral error messages
        await interaction.response.defer(ephemeral=True)

        if not is_rp_enabled(interaction.channel):
            msg = f"RP is not enabled in this channel ({get_channel_id(interaction.channel)}). Invoked by {interaction.user}."
            await interaction.followup.send(msg, ephemeral=True)
            logger.warning(msg)
            return

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            msg = f"RP scene messages can only be sent in text channels. Invoked by {interaction.user}."
            await interaction.followup.send(msg, ephemeral=True)
            logger.warning(msg)
            return

        scene_text: str = setting

        if location:
            scene_text = f"{location} {scene_text}"

        if time_of_day:
            scene_text = f"{scene_text} - {time_of_day}"

        if parenthetical:
            scene_text = f"{scene_text} ({parenthetical})"

        try:
            response: discord.Message = await channel.send(
                **build_discord_embed(
                    description=(
                        f"```\n"
                        f"{scene_text.upper()}\n"
                        f"```"
                    ),
                    timestamp=None,
                    color=discord.Color(int(color, 16)) if color else discord.Color.blue(),
                )
            )

            await interaction.delete_original_response()

            if response:
                await impersonation_history.add(interaction.user.id, response.id)

            logger.debug(f'Sent rp_scene message from "{interaction.user}" in "{channel.id}": "{scene_text.replace("\n", "\\n")}"')

        except Exception as e:
            if not interaction.response.is_done():
                await interaction.delete_original_response()

            logger.warning(f'Failed to send rp_scene message: {e}')

    @app_commands.command(
        name="rp_default",
        description="Set or unset a default profile for your RP messages"
    )
    @app_commands.describe(
        trigger="The trigger of the impersonation profile to set as default. Leave empty to unset."
    )
    @app_commands.autocomplete(trigger=_autocomplete_trigger)
    async def rp_default(self, interaction: Interaction, trigger: str | None = None):
        """Set or unset a default profile for your RP messages."""
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        trigger = trigger.strip() if trigger else None

        if not trigger:
            await impersonation_default.unset(user_id)
            await interaction.followup.send(
                **build_discord_embed(
                    title="✅ Default RP Profile Unset",
                    description="Your default RP profile has been unset."
                ),
                ephemeral=True
            )
            logger.debug(f'User {interaction.user} unset their default RP profile.')
            return

        profile: ImpersonationProfile | None = get_profile_by_trigger_and_user(trigger, interaction.user)

        if not profile:
            error: str = (f'User {interaction.user} attempted to set their default RP profile to unknown trigger "{trigger}".')
            await interaction.followup.send(**build_discord_embed(description=error), ephemeral=True)
            logger.warning(error)
            return

        await impersonation_default.set(user_id, trigger)
        await interaction.followup.send(
            **build_discord_embed_with_thumbnail(
                title="✅ Default RP Profile Set",
                description=(
                    f"Your default RP profile has been set to **{profile.username}** "
                    f"(`{trigger}`).\n\n"
                    f"You can now send messages normally in chat without specifying a trigger, "
                    f"though you can still specify a different trigger if desired."
                ),
                thumbnail_url=profile.bust_url if profile.bust_url else profile.avatar_url,
            ),
            ephemeral=True,
        )

        logger.debug(f'User {interaction.user} set their default RP profile to "{profile.username}" with trigger "{trigger}".')

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
            logger.warning(msg)
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
            f"{interaction.guild.id}/{channel.name if channel else 'Unknown'} - {status_log}"
        )
