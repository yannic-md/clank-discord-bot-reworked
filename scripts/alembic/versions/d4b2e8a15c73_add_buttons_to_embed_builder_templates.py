"""add buttons to embed builder templates

Revision ID: d4b2e8a15c73
Revises: c3f1a7d92b64
Create Date: 2026-11-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b2e8a15c73'
down_revision: Union[str, Sequence[str], None] = 'c3f1a7d92b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('builder_embed_templates', sa.Column('components', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('builder_embed_templates', 'components')
