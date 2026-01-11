from bot.cogs.impersonation.message_tracker import ImpersonationMessageTracker
from bot.cogs.impersonation.command_handler import ImpersonationCommandHandler
from discord.ext import commands


async def setup(bot: commands.Bot) -> None:
    """
    Async setup function to load the Impersonation cogs.

    This is called automatically when the extension is loaded.

    Args:
        bot: The bot instance to attach the cogs to.
    """
    await bot.add_cog(ImpersonationMessageTracker(bot))
    await bot.add_cog(ImpersonationCommandHandler(bot))
