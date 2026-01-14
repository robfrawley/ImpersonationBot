import json
from zoneinfo import ZoneInfo
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot import ENV_FILE_PATH


class ImpersonationProfile(BaseModel):
    """Represents a single impersonation profile for the bot."""

    triggers: list[str]
    username: str
    avatar_url: str
    bust_url: str
    dossier_url: str | None = None
    keyart_url: str | None = None
    power_url: str | None = None
    restricted_users: list[int] | None = None

    def is_allowed_user(self, user_id: int) -> bool:
        """Check if a user ID is allowed to use this profile.

        Args:
            user_id: The Discord user ID to check.

        Returns:
            True if the user is allowed to use this profile, False otherwise.
        """
        if self.restricted_users is None:
            return True
        return user_id in self.restricted_users


class SettingsManager(BaseSettings):
    """Bot settings loaded from environment variables."""

    impersonation_profiles: list[ImpersonationProfile] = []
    discord_token: str = Field()
    sqlite_db_path: str = Field()
    debug_mode: bool = Field(default=False)
    bot_time_zone: ZoneInfo = Field(default=ZoneInfo("UTC"))
    enabled_channels: list[int] = Field(default=[])

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        env_nested_delimiter="__",
    )

    @field_validator("sqlite_db_path", mode="before")
    @classmethod
    def make_sqlite_db_path_absolute(cls, v: str) -> str:
        """Ensure sqlite_db_path is an absolute path."""
        if not v:
            raise ValueError("sqlite_db_path cannot be empty")

        return str(Path(v).expanduser().resolve())

    @field_validator("bot_time_zone", mode="before")
    @classmethod
    def normalize_bot_time_zone(cls, v):
        """Convert string time zone to ZoneInfo if needed."""
        if isinstance(v, str):
            return ZoneInfo(v)
        return v

    @field_validator("enabled_channels", mode="before")
    @classmethod
    def parse_enabled_channels_json(cls, v):
        """Parse JSON string for enabled channels if needed."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("impersonation_profiles", mode="before")
    @classmethod
    def preprocess_profiles(cls, v):
        """Normalize profiles and ensure no duplicate triggers exist."""
        if isinstance(v, dict):
            # Sort dict keys numerically and convert to list
            v = [v[k] for k in sorted(v.keys(), key=int)]

        all_triggers: set[str] = set()

        for profile in v:
            if "restricted_users" in profile and isinstance(profile["restricted_users"], str):
                profile["restricted_users"] = [int(x) for x in json.loads(profile["restricted_users"])]

            # Ensure triggers is a list
            if isinstance(profile.get("triggers"), str):
                profile["triggers"] = json.loads(profile["triggers"])

            triggers_list = profile.get("triggers", [])
            if not isinstance(triggers_list, list):
                raise ValueError(f"Triggers must be a list, got {triggers_list!r}")

            # Check for duplicate triggers across all profiles
            duplicates = set(triggers_list) & all_triggers
            if duplicates:
                raise ValueError(
                    f"Duplicate triggers found across profiles: {', '.join(duplicates)}"
                )

            # Add triggers to global set
            all_triggers.update(triggers_list)

        return v


# Instantiate settings
settings = SettingsManager() # type: ignore
