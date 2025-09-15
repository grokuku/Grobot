"""Create uploaded_files table

Revision ID: 93be5119cdd8
Revises: 65bbf3afc4fe
Create Date: 2025-08-12 21:11:57.667261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '93be5119cdd8'
down_revision: Union[str, Sequence[str], None] = '65bbf3afc4fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('uploaded_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(), nullable=False),
    sa.Column('bot_id', sa.Integer(), nullable=False),
    sa.Column('owner_discord_id', sa.String(), nullable=False),
    sa.Column('access_level', sa.String(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_type', sa.String(), nullable=False),
    sa.Column('file_family', sa.String(), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('file_metadata', postgresql.JSONB(), nullable=True),
    sa.Column('storage_path', sa.String(), nullable=False),
    sa.Column('storage_status', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('last_accessed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['bot_id'], ['bots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uploaded_files_owner_discord_id'), 'uploaded_files', ['owner_discord_id'], unique=False)
    op.create_index(op.f('ix_uploaded_files_uuid'), 'uploaded_files', ['uuid'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_uploaded_files_uuid'), table_name='uploaded_files')
    op.drop_index(op.f('ix_uploaded_files_owner_discord_id'), table_name='uploaded_files')
    op.drop_table('uploaded_files')