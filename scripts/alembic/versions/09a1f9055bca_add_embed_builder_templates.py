"""add embed builder templates

Revision ID: 09a1f9055bca
Revises: a23f95225939
Create Date: 2026-08-29 17:48:19.466208

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "09a1f9055bca"
down_revision: Union[str, Sequence[str], None] = "a23f95225939"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "embed_builder_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=100), nullable=False),
        sa.Column("message_content", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("embeds", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_embed_builder_template_user_name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("embed_builder_templates")
