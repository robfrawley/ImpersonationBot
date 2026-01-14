import discord

from bot.core.bot import Bot
from bot.utils.settings import settings
from bot.utils.logger import logger


# ----------------------------------------------------------------------
# Bot setup
# ----------------------------------------------------------------------

intents = discord.Intents.all()
intents.message_content = True

bot = Bot(
    command_prefix="i!",
    intents=intents,
    help_command=None,
)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main() -> None:
    try:
        bot.run(settings.discord_token)
    except KeyboardInterrupt:
        logger.info('Bot is shutting down...')
    finally:
        logger.info('Bot has exited...')


if __name__ == "__main__":
    main()
