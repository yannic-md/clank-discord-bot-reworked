from dataclasses import dataclass

BUILDER_VIEW_TIMEOUT: float = 900.0
"""How long (seconds) a builder screen stays interactive without any input."""


@dataclass
class WebhookSender:
    """Custom sender identity a message can be sent with, via a channel webhook."""

    username: str | None = None
    avatar_url: str | None = None
    webhook_url: str | None = None
    validated_channel_id: int | None = None
    explicit_url: bool = False
    display_name: str | None = None
    """The webhook's own name, captured for status display only - never sent as an
    override, so a URL-only webhook (no explicit `username`) keeps its own identity."""

    @property
    def enabled(self) -> bool:
        """Whether any custom sender identity (name, avatar or webhook) is configured."""
        return self.username is not None or self.avatar_url is not None or self.webhook_url is not None
