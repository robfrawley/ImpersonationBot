import discord
from discord import Message
from discord.ext import commands
from discord.app_commands import AppCommand

from bot.utils.logger import logger
from bot.utils.settings import settings
from bot.db.database import Database
from bot.db.impersonation_default import ImpersonationDefaultRepo
from bot.db.impersonation_history import ImpersonationHistoryRepo

# List of bot extensions (cogs) to load
EXTENSIONS: list[str] = [
    "bot.cogs.impersonation",
]

# ----------------------------------------------------------------------
# Globals
# ----------------------------------------------------------------------

db = Database(settings.sqlite_db_path)
impersonation_default: ImpersonationDefaultRepo | None = None
impersonation_history: ImpersonationHistoryRepo | None = None


class Bot(commands.Bot):
    """Custom Discord bot with automatic cog loading and command syncing."""

    def __init__(self, command_prefix: str, intents: discord.Intents, **kwargs) -> None:
        """
        Initialize the bot.

        Args:
            command_prefix: Prefix for text commands.
            intents: Discord bot intents.
            **kwargs: Additional arguments to pass to commands.Bot.
        """
        super().__init__(command_prefix, intents=intents, **kwargs)

    async def on_ready(self) -> None:
        """Called when the bot has connected and is ready."""
        global impersonation_default
        global impersonation_history

        await db.connect()

        impersonation_default = ImpersonationDefaultRepo(db)
        impersonation_history = ImpersonationHistoryRepo(db)

        await impersonation_default.init_schema()
        await impersonation_history.init_schema()

        logger.debug("Database connected and ImpersonationDefaultRepo initialized.")
        logger.info(f"Bot is ready. Logged in as {self.user} (ID: {self.user.id})")

        logger.info("Loading extensions...")

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.debug(f'- "{ext}" (success)')
            except Exception as e:
                logger.warning(f'- "{ext}" (failure: {e})')

        logger.info("Syncing commands...")
        synced: list[AppCommand] = await self.tree.sync()
        logger.log_commands(synced)

        if self.user:
            logger.info(f'User "{self.user.name}" with ID "{self.user.id}" is ready.')
        else:
            logger.warning("Bot user is None on ready event!")

    async def on_message(self, message: Message) -> None:
        """
        Called when a message is received.

        Args:
            message: The Discord message object.
        """
        # Ignore messages from bots
        if message.author.bot:
            return

        # List of cogs and functions to process messages
        COGS_TO_TRACK: list[tuple[str, str]] = [
            ("ImpersonationMessageTracker", "track_messages"),
        ]

        for cog_name, func_name in COGS_TO_TRACK:
            cog = self.get_cog(cog_name)
            if not cog:
                logger.warning(f'Cog "{cog_name}" not found')
                continue

            func = getattr(cog, func_name, None)
            if not func:
                logger.warning(f'Cog "{cog_name}" has no function "{func_name}"')
                continue

            await func(message)

        # Ensure commands are processed
        await self.process_commands(message)
