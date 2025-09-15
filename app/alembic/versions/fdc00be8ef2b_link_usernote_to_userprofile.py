"""Link UserNote to UserProfile

Revision ID: fdc00be8ef2b
Revises: 15100589eba8
Create Date: 2025-09-12 14:11:01.192547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fdc00be8ef2b'
down_revision: Union[str, Sequence[str], None] = '15100589eba8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### Phase 1: Add the new column, but allow it to be NULL temporarily ###
    op.add_column('user_notes', sa.Column('user_profile_id', sa.Integer(), nullable=True))

    # ### Phase 2: Perform a data migration to populate the new column ###
    # This SQL statement finds the matching user_profile for each note and copies its ID.
    op.execute("""
        UPDATE user_notes
        SET user_profile_id = up.id
        FROM user_profiles AS up
        WHERE
            up.bot_id = user_notes.bot_id AND
            up.discord_user_id = user_notes.user_discord_id AND
            up.server_discord_id = user_notes.server_discord_id
    """)
    
    # ### NOUVEAU - Phase 2.5: Delete any orphan notes that couldn't be matched ###
    op.execute("""
        DELETE FROM user_notes WHERE user_profile_id IS NULL
    """)

    # ### Phase 3: Now that all rows are populated, enforce the NOT NULL constraint ###
    op.alter_column('user_notes', 'user_profile_id', nullable=False)


    # ### Phase 4: Clean up the old structure (as auto-generated) ###
    op.drop_index(op.f('ix_user_notes_bot_id'), table_name='user_notes', if_exists=True)
    op.drop_index(op.f('ix_user_notes_server_discord_id'), table_name='user_notes', if_exists=True)
    op.drop_index(op.f('ix_user_notes_user_discord_id'), table_name='user_notes', if_exists=True)
    op.create_index(op.f('ix_user_notes_user_profile_id'), 'user_notes', ['user_profile_id'], unique=False)

    # Create the foreign key constraint AFTER data is populated and column is ready
    op.create_foreign_key(op.f('user_notes_user_profile_id_fkey'), 'user_notes', 'user_profiles', ['user_profile_id'], ['id'])

    # Drop the old foreign key and redundant columns
    op.drop_constraint('user_notes_bot_id_fkey', 'user_notes', type_='foreignkey', if_exists=True)
    op.drop_column('user_notes', 'bot_id')
    op.drop_column('user_notes', 'user_discord_id')
    op.drop_column('user_notes', 'server_discord_id')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### Downgrade requires re-creating columns and back-populating data in reverse ###
    op.add_column('user_notes', sa.Column('server_discord_id', sa.BIGINT(), autoincrement=False, nullable=True))
    op.add_column('user_notes', sa.Column('user_discord_id', sa.BIGINT(), autoincrement=False, nullable=True))
    op.add_column('user_notes', sa.Column('bot_id', sa.INTEGER(), autoincrement=False, nullable=True))

    # Back-populate the old columns from the user_profile table
    op.execute("""
        UPDATE user_notes
        SET
            bot_id = up.bot_id,
            user_discord_id = up.discord_user_id,
            server_discord_id = up.server_discord_id
        FROM user_profiles AS up
        WHERE
            up.id = user_notes.user_profile_id
    """)

    # Make the old columns non-nullable
    op.alter_column('user_notes', 'server_discord_id', nullable=False)
    op.alter_column('user_notes', 'user_discord_id', nullable=False)
    op.alter_column('user_notes', 'bot_id', nullable=False)

    # Restore old indexes and foreign key
    op.create_foreign_key('user_notes_bot_id_fkey', 'user_notes', 'bots', ['bot_id'], ['id'])
    op.create_index(op.f('ix_user_notes_user_discord_id'), 'user_notes', ['user_discord_id'], unique=False)
    op.create_index(op.f('ix_user_notes_server_discord_id'), 'user_notes', ['server_discord_id'], unique=False)
    op.create_index(op.f('ix_user_notes_bot_id'), 'user_notes', ['bot_id'], unique=False)

    # Drop the new structure
    op.drop_constraint(op.f('user_notes_user_profile_id_fkey'), 'user_notes', type_='foreignkey')
    op.drop_index(op.f('ix_user_notes_user_profile_id'), table_name='user_notes')
    op.drop_column('user_notes', 'user_profile_id')
    # ### end Alembic commands ###