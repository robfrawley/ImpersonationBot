import discord
from discord import Message
from discord.ext import commands

from bot.utils.settings import settings
from bot.utils.logger import logger
from bot.db.database import db
from bot.db.impersonation_default import impersonation_default
from bot.db.impersonation_history import impersonation_history


# List of bot extensions to load
BOT_LOAD_EXTENSIONS: list[str] = [
    "bot.cogs.impersonation",
]

# List of callable to track messages
BOT_MESSAGE_TRACKER: list[tuple[str, str]] = [
    ("ImpersonationMessageTracker", "track_messages"),
]


class Bot(commands.Bot):

    async def setup_hook(self) -> None:
        logger.debug('Running setup hook...')

        logger.info('Setting up database...')
        await db.connect()
        await impersonation_default.init_schema()
        await impersonation_history.init_schema()

        logger.info('Loading extensions...')
        for ext in BOT_LOAD_EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.debug(f'- "{ext}" (success)')
            except Exception as e:
                logger.warning(f'- "{ext}" (failure: {e})')

        logger.info('Syncing commands...')
        logger.log_commands(await self.tree.sync())

    async def on_ready(self) -> None:
        logger.debug('Running on-ready hook...')

        if not self.user:
            raise Exception("Bot user information is None.")

        logger.info(f'User "{self.user.name}" with ID "{self.user.id}" is logged in and ready.')

    async def close(self) -> None:
        logger.debug('Closing Discord connection...')
        await super().close()

        try:
            logger.debug('Closing database connection...')
            await db.close()
        except Exception as e:
            logger.warning(f'Error closing database connection: {e}')

    async def on_message(self, message: Message) -> None:
        if message.author.bot:
            return

        for class_name, method_name in BOT_MESSAGE_TRACKER:

            cog_instance = self.get_cog(class_name)
            if not cog_instance:
                logger.warning(f'Message tracker class "{class_name}" not found.')
                continue

            method_callable = getattr(cog_instance, method_name, None)
            if not method_callable:
                logger.warning(f'Message tracker class "{class_name}" has no method "{method_name}".')
                continue

            await method_callable(message)

        await self.process_commands(message)
