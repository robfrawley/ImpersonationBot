from bot.cogs.impersonation.manager import ImpersonationManager
from bot.cogs.impersonation.commands import ImpersonationCommands
from discord.ext import commands


async def setup(bot: commands.Bot) -> None:
    """
    Async setup function to load the Impersonation cogs.

    This is called automatically when the extension is loaded.

    Args:
        bot: The bot instance to attach the cogs to.
    """
    await bot.add_cog(ImpersonationManager(bot))
    await bot.add_cog(ImpersonationCommands(bot))
