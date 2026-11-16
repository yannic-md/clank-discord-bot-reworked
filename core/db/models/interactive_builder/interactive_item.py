from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base


class InteractiveItem(Base):
    """A button, dropdown or form a user attached to a builder message.

    The message itself only carries the item's `id` inside its `custom_id`; what happens on a
    click (actions) and who may click (conditions) lives in `config`, so it survives bot restarts.

    `config` is a JSON object that is always read and written as one whole unit and is never
    queried, joined or sorted on (see the interactive builder's `ItemConfig`).

    `channel_id` and `message_id` stay `NULL` until the message has actually been sent, and are
    used to clean the row up again once the message, its channel or the guild is gone.
    """

    __tablename__ = "builder_interactive_items"
    __table_args__ = (
        Index("ix_interactive_items_guild_id", "guild_id"),
        Index("ix_interactive_items_channel_id", "channel_id"),
        Index("ix_interactive_items_message_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class InteractiveItemUse(Base):
    """One user's use of an item (or of one option of a dropdown), backing the "once per user" condition.

    The composite primary key is what makes reserving a use atomic: a second insert for the same
    `(item_id, option_key, user_id)` is rejected by the database instead of racing past a check.
    `option_key` is the empty string for items without options (buttons, forms).
    """

    __tablename__ = "builder_interactive_item_uses"

    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("builder_interactive_items.id", ondelete="CASCADE"), primary_key=True
    )
    option_key: Mapped[str] = mapped_column(String(64), primary_key=True, default="")
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
