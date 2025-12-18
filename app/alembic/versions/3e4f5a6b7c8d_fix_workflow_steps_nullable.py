"""fix workflow_steps mcp_server_id nullable

Revision ID: 3e4f5a6b7c8d
Revises: f963c9992c35
Create Date: 2025-12-18 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e4f5a6b7c8d'
down_revision: Union[str, Sequence[str], None] = 'f963c9992c35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Allow mcp_server_id to be NULL for internal tools
    op.alter_column('workflow_steps', 'mcp_server_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert mcp_server_id to NOT NULL (warning: this may fail if null values exist)
    op.alter_column('workflow_steps', 'mcp_server_id',
               existing_type=sa.INTEGER(),
               nullable=False)