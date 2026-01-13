from datetime import datetime

import discord

from bot.core.bot import Database
from bot.utils.logger import logger
from bot.utils.settings import ImpersonationProfile, settings


class WebhookModel:
    """Container for a webhook and its local creation timestamp."""

    def __init__(self, webhook: discord.Webhook) -> None:
        """Initialize the model with the backing webhook.

        Args:
            webhook (discord.Webhook): Discord webhook instance.
        """
        self.webhook = webhook
        self.created_at = datetime.now(settings.bot_time_zone)

    def name(self) -> str | None:
        """Return the webhook's name.

        Returns:
            str | None: The webhook name, if available.
        """
        return self.webhook.name

class WebhookManager:
    def __init__(self, db: Database, channel: discord.TextChannel, limit: int = 15) -> None:
        """Manage webhooks for a specific channel.

        Args:
            db (Database): The database instance.
            channel (discord.TextChannel): The discord text channel to handle webhooks for.
            limit (int, optional): the webhook limit to enforce. Defaults to 15.
        """
        self.db = db
        self.channel = channel
        self.webhooks: list[WebhookModel] = []
        self.limit = max(1, limit)
        self.initialized = False

    async def initialize(self) -> None:
        """Initialize the manager by populating existing webhooks once."""
        if not self.initialized:
            await self._populateWebhooks()
            self.initialized = True

    async def get_for_profile(self, profile: ImpersonationProfile) -> discord.Webhook:
        """Get or create a webhook for the given impersonation profile.

        Args:
            profile (ImpersonationProfile): The rp impersonation profile to get the webhook for.

        Raises:
            Exception: If webhook creation fails.

        Returns:
            discord.Webhook: Returns the correct webhook for the desired impersonation profile.
        """
        await self.initialize()

        profile_webhook_name = f"RP:{profile.username}"

        # Check for existing webhook
        for webhook_model in self.webhooks:
            if webhook_model.name() == profile_webhook_name:
                logger.debug(
                    f'Using existing webhook "{webhook_model.name()}" for profile "{profile.username}".'
                )
                return webhook_model.webhook

        # If limit reached, delete the oldest webhook first.
        if len(self.webhooks) > 0 and len(self.webhooks) >= self.limit:
            oldest_webhook_model = self.webhooks.pop()
            logger.debug(
                f'Deleting oldest webhook "{oldest_webhook_model.name()}" to make space.'
            )
            await oldest_webhook_model.webhook.delete()

        # No matching webhook found, create a new one
        avatar_bytes = None
        if profile.avatar_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(profile.avatar_url) as resp:
                        if resp.status == 200:
                            avatar_bytes = await resp.read()
            except Exception:
                # Fallback to no avatar if download fails.
                pass

        try:
            webhook: discord.Webhook = await self.channel.create_webhook(
                name=profile_webhook_name,
                avatar=avatar_bytes,
                reason=f'Creating webhook for impersonation profile "{profile.username}"',
            )
        except Exception:
            logger.warning(
                f'Failed to create webhook for profile "{profile.username}" in channel "{self.channel.id}".'
            )
            raise Exception("Webhook creation failed.")

        logger.debug(
            f'Creating new webhook "{profile_webhook_name}" for profile "{profile.username}" '
            f'in channel "{self.channel.id}".'
        )

        webhook_model = WebhookModel(webhook=webhook)
        self.webhooks.append(webhook_model)
        self._order_webhooks()

        return webhook

    async def _populateWebhooks(self) -> None:
        """Populate the local webhook cache from the channel."""
        webhooks = await self.channel.webhooks()

        logger.debug(f'Found {len(webhooks)} existing webhooks for channel "{self.channel.id}".')

        for webhook in webhooks:
            if webhook.user == self.channel.guild.me and (webhook.name.startswith("RP:") if webhook.name else False):
                logger.debug(
                    f'Adding webhook "{webhook.name}" to manager for channel "{self.channel.id}".'
                )
                self.webhooks.append(WebhookModel(webhook=webhook))

        self._order_webhooks()

    def _order_webhooks(self) -> None:
        """Sort webhooks by creation time, newest first."""
        self.webhooks.sort(key=lambda wm: wm.created_at, reverse=True)
