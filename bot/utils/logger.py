import os
import json
import sys
import datetime
import discord
from discord.app_commands import AppCommand
from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings
from bot.utils.settings import settings, ImpersonationProfile

# console logger class handles writing logs to console with colors and timestamps
class ConsoleLogger:
    def __init__(self, debug_enabled: bool = True, timezone: ZoneInfo = ZoneInfo("UTC")):
        self.debug_enabled = debug_enabled
        self.timezone = timezone

    def _log(self, level: str, message: str, level_color: str = ""):
        timestamp = datetime.datetime.now(tz=self.timezone).strftime("%Y-%m-%d %H:%M:%S")
        dim_white = "\033[37;2m"
        reset_code = "\033[0m"
        padded_level = f"{level.ljust(8)}"
        colored_level = f"{level_color}{padded_level}{reset_code}"
        print(f"{dim_white}{timestamp}{reset_code} {colored_level} {message}", file=sys.stdout)

    def info(self, message: str):
        self._log("INFO", message, level_color="\033[34;1m")

    def debug(self, message: str):
        if self.debug_enabled:
            self._log("DEBUG", message, level_color="\033[93m")

    def warn(self, message: str):
        self.warn('!!!!!!!!!!!!!!!! UPDATE CODE CALL FROM WARNING TO WARN!')
        self.warning(message)

    def warning(self, message: str):
        self._log("WARN", message, level_color="\033[91m")

    # log complete settings dump loaded from environment
    def log_settings(self, settings: BaseSettings):
        self.info("Loaded configuration...")

        fields = settings.model_fields.keys()
        values = {field: getattr(settings, field) for field in fields}
        maxlen = max(len(name) for name in fields)

        for name, value in values.items():
            if name == "impersonation_profiles":
                p_key_maxlen = max(len(field_name) for field_name in ImpersonationProfile.model_fields)

                self.debug(f'- ' + f'"{name}"'.ljust(maxlen + 2) + f' = [')

                for idx, profile in enumerate(value):
                    self.debug(f"    \"profile-{idx + 1}\" = [")

                    for p_name, p_value in profile.model_dump().items():
                        self.debug(f'      ' + f'"{p_name}"'.ljust(p_key_maxlen + 2) + f' = "{p_value}"')

                    self.debug(f"    ]")

                self.debug(f"  ]")
            else:
                self.debug(f'- ' + f'"{name}"'.ljust(maxlen + 2) + f' = "{value}"')

    # log synced commands
    def log_commands(self, synced: AppCommand):

        entries: list[tuple[str, str]] = []

        for command in synced:
            scope = "global" if command.guild_id is None else f"guild={command.guild_id}"
            entries.append((f"- \"{command.name}\"", scope))

        max_len = max((len(cmd) for cmd, _ in entries), default=0)

        logger.info(f"Synced \"{len(synced)}\" commands...")
        
        for cmd, scope in entries:
            logger.debug(f"{cmd.ljust(max_len)} ({scope})")


# initialize logger and dump settings
logger = ConsoleLogger(debug_enabled=settings.debug_mode, timezone=settings.bot_timezone)
logger.log_settings(settings)
