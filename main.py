import discord
from bot.core.bot import Bot
from bot.utils.settings import settings

# ----------------------------------------------------------------------
# Bot Entry Point
# ----------------------------------------------------------------------

def main() -> None:
    """Initialize and run the Discord bot."""
    # Configure intents
    intents = discord.Intents.all()
    intents.message_content = True  # Enable message content intent

    # Initialize bot
    bot = Bot(
        command_prefix="i!",
        intents=intents,
        help_command=None,  # Disable default help command
    )

    # Run bot using token from settings
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
