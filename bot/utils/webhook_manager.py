from datetime import datetime

import discord

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
        self.update_timestamp()

    def name(self) -> str | None:
        """Return the webhook's name.

        Returns:
            str | None: The webhook name, if available.
        """
        return self.webhook.name

    def update_timestamp(self) -> None:
        """Update the creation timestamp to now."""
        self.created_at = datetime.now(settings.bot_time_zone)

class WebhookManager:
    def __init__(self, limit: int = 15) -> None:
        """Manage webhooks for a specific channel.

        Args:
            limit (int, optional): the webhook limit to enforce. Defaults to 15.
        """
        self.webhooks: dict[int, list[WebhookModel]] = {}
        self.limit: int = max(1, limit)

    async def initialize(self, channel: discord.TextChannel) -> None:
        if not channel.id in self.webhooks:
            await self._populateWebhooks(channel)

    async def get_for_profile(self, profile: ImpersonationProfile, channel: discord.TextChannel) -> discord.Webhook:
        """Get or create a webhook for the given impersonation profile.

        Args:
            profile (ImpersonationProfile): The rp impersonation profile to get the webhook for.

        Raises:
            Exception: If webhook creation fails.

        Returns:
            discord.Webhook: Returns the correct webhook for the desired impersonation profile.
        """

        await self.initialize(channel)

        profile_webhook_name = self._get_profile_identifier(profile)

        # Check for existing webhook
        for webhook_model in self.webhooks[channel.id]:
            if webhook_model.name() == profile_webhook_name:
                logger.debug(
                    f'Using existing webhook "{webhook_model.name()}" with ID "{webhook_model.webhook.id}" for profile "{profile.username}".'
                )
                webhook_model.update_timestamp()
                return webhook_model.webhook

        # If limit reached, delete the oldest webhook first.
        if len(self.webhooks[channel.id]) > 0 and len(self.webhooks[channel.id]) >= self.limit:
            await self._delete_oldest_webhook(channel)

        return await self._create_webhook(channel, profile)

    async def _populateWebhooks(self, channel: discord.TextChannel) -> None:
        """Populate the local webhook cache from the channel."""
        assert channel is not None, "WebhookManager channel is not set."

        self.webhooks.setdefault(channel.id, [])
        webhooks = await channel.webhooks()

        logger.debug(f'Found {len(webhooks)} existing webhooks for channel "{channel.id}".')

        for webhook in webhooks:
            if webhook.user == channel.guild.me and (webhook.name.startswith("RP:") if webhook.name else False):
                logger.debug(
                    f'Caching webhook "{webhook.name}" with ID "{webhook.id}" to manager for channel "{channel.id}".'
                )
                self.webhooks[channel.id].append(WebhookModel(webhook=webhook))

    async def _create_webhook(self, channel: discord.TextChannel, profile: ImpersonationProfile) -> discord.Webhook:
        profile_webhook_name = self._get_profile_identifier(profile)
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
            webhook: discord.Webhook = await channel.create_webhook(
                name=profile_webhook_name,
                avatar=avatar_bytes,
                reason=f'Creating webhook for impersonation profile "{profile.username}"',
            )
        except Exception:
            logger.warning(
                f'Failed to create webhook for profile "{profile.username}" with name "{profile_webhook_name}" in channel "{channel.id}".'
            )
            raise Exception("Webhook creation failed.")

        webhook_model = WebhookModel(webhook=webhook)
        self.webhooks.setdefault(channel.id, []).append(webhook_model)

        logger.debug(
            f'Created new webhook "{profile_webhook_name}" with ID "{webhook.id}" for profile "{profile.username}" '
            f'in channel "{channel.id}".'
        )

        return webhook

    async def _delete_oldest_webhook(self, channel: discord.TextChannel) -> None:
        """Delete the oldest webhook in the channel to enforce the limit."""
        if self._is_channel_initialized(channel.id):
            self._order_webhooks(channel.id)
            oldest_webhook_model = self.webhooks[channel.id][-1]
            try:
                await oldest_webhook_model.webhook.delete(
                    reason="Deleting oldest webhook to enforce limit."
                )
                logger.debug(
                    f'Deleted oldest webhook "{oldest_webhook_model.name()}" with ID "{oldest_webhook_model.webhook.id}" '
                    f'in channel "{channel.id}" to enforce limit.'
                )
            except Exception as e:
                logger.warning(
                    f'Failed to delete oldest webhook "{oldest_webhook_model.name()}" with ID "{oldest_webhook_model.webhook.id}" '
                    f'in channel "{channel.id}": {e}'
                )
            self.webhooks[channel.id].pop(-1)

    def _order_webhooks(self, channel_id: int) -> None:
        """Sort webhooks by creation time, newest first."""
        if self._is_channel_initialized(channel_id):
            self.webhooks[channel_id].sort(key=lambda wm: wm.created_at, reverse=True)

    def _is_channel_initialized(self, channel_id: int) -> bool:
        """Check if the channel has been initialized in the manager.

        Args:
            channel_id (int): The Discord channel ID.
        Returns:
            bool: True if initialized, False otherwise.
        """
        return channel_id in self.webhooks and len(self.webhooks[channel_id]) > 0

    def _get_profile_identifier(self, profile: ImpersonationProfile) -> str:
        """Get the webhook name for a given profile.

        Args:
            profile (ImpersonationProfile): The impersonation profile.
        Returns:
            str: The webhook name.
        """
        return f"RP:{profile.username}"

webhook_manager: WebhookManager = WebhookManager()
