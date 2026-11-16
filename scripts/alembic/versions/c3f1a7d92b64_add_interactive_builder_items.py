"""add interactive builder items

Revision ID: c3f1a7d92b64
Revises: a085e9bf0f7f
Create Date: 2026-11-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a7d92b64'
down_revision: Union[str, Sequence[str], None] = 'a085e9bf0f7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('builder_interactive_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('guild_id', sa.BigInteger(), nullable=False),
    sa.Column('creator_id', sa.BigInteger(), nullable=False),
    sa.Column('channel_id', sa.BigInteger(), nullable=True),
    sa.Column('message_id', sa.BigInteger(), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interactive_items_channel_id', 'builder_interactive_items', ['channel_id'], unique=False)
    op.create_index('ix_interactive_items_guild_id', 'builder_interactive_items', ['guild_id'], unique=False)
    op.create_index('ix_interactive_items_message_id', 'builder_interactive_items', ['message_id'], unique=False)
    op.create_table('builder_interactive_item_uses',
    sa.Column('item_id', sa.BigInteger(), nullable=False),
    sa.Column('option_key', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('used_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['builder_interactive_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', 'option_key', 'user_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('builder_interactive_item_uses')
    op.drop_index('ix_interactive_items_message_id', table_name='builder_interactive_items')
    op.drop_index('ix_interactive_items_guild_id', table_name='builder_interactive_items')
    op.drop_index('ix_interactive_items_channel_id', table_name='builder_interactive_items')
    op.drop_table('builder_interactive_items')
