from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base
from core.discord_api.limits import MAX_SELECT_OPTION_LABEL


class ContainerTemplate(Base):
    """A saved `/container-builder` draft a user can reload later.

    One row per template, owned by the Discord user who created it: templates are
    per-user and follow that user across every guild, not shared within a guild.

    `components` holds the message's component tree as a JSON array of plain dicts
    (see the container builder's template serialization). It is always read and
    written as one whole unit and is never queried, joined or sorted on.
    """

    __tablename__ = "container_builder_templates"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_container_builder_template_user_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(MAX_SELECT_OPTION_LABEL), nullable=False)
    icon: Mapped[str] = mapped_column(String(MAX_SELECT_OPTION_LABEL), nullable=False)
    components: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
