"""Add default prompt for analyze_file tool

Revision ID: 68a1e2913b5a
Revises: 93be5119cdd8
Create Date: 2025-08-13 15:03:28.207983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json

# revision identifiers, used by Alembic.
revision: str = '68a1e2913b5a'
down_revision: Union[str, Sequence[str], None] = '93be5119cdd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the new default value for the tool_prompts_default JSON object
new_tool_prompts_default = {
    "get_current_time": (
        "This tool allows you to know the current date and time. "
        "You do not need to provide any arguments to it. "
        "Call this tool if the user asks you for the time, the date, "
        "or information related to the present moment."
    ),
    "search_files": (
        "This tool allows you to search for files stored in the system. "
        "You can search by filename, file_family (e.g., 'image', 'text'), or owner_id (a Discord user ID). "
        "All parameters are optional. Use it when a user asks to find, list, or check for a file."
    ),
    "analyze_file": (
        "This tool analyzes the content of a text-based file and generates a summary. "
        "It takes one mandatory argument: 'uuid', which is the unique identifier of the file to analyze. "
        "The summary is then stored in the file's metadata. "
        "Use this tool when a user explicitly asks to analyze, summarize, or describe a specific file."
    ),
}

# Define the old default value for the downgrade path.
old_tool_prompts_default = {
    "get_current_time": (
        "This tool allows you to know the current date and time. "
        "You do not need to provide any arguments to it. "
        "Call this tool if the user asks you for the time, the date, "
        "or information related to the present moment."
    ),
    "search_files": (
        "This tool allows you to search for files stored in the system. "
        "You can search by filename, file_family (e.g., 'image', 'text'), or owner_id (a Discord user ID). "
        "All parameters are optional. Use it when a user asks to find, list, or check for a file."
    ),
}

def escape_single_quotes(json_string: str) -> str:
    """Escapes single quotes for safe inclusion in a SQL string."""
    return json_string.replace("'", "''")

def upgrade() -> None:
    """Upgrade schema."""
    new_prompts_json = json.dumps(new_tool_prompts_default)
    new_prompts_sql_safe = escape_single_quotes(new_prompts_json)

    # We update the default value for the column.
    op.alter_column(
        'global_settings',
        'tool_prompts_default',
        server_default=sa.text(f"'{new_prompts_sql_safe}'::jsonb"),
        existing_type=sa.JSON(),
        nullable=False
    )
    # We also update the existing row to use the new default.
    op.execute(
        f"UPDATE global_settings SET tool_prompts_default = '{new_prompts_sql_safe}'::jsonb WHERE id = 1"
    )


def downgrade() -> None:
    """Downgrade schema."""
    old_prompts_json = json.dumps(old_tool_prompts_default)
    old_prompts_sql_safe = escape_single_quotes(old_prompts_json)

    # We revert the default value for the column.
    op.alter_column(
        'global_settings',
        'tool_prompts_default',
        server_default=sa.text(f"'{old_prompts_sql_safe}'::jsonb"),
        existing_type=sa.JSON(),
        nullable=False
    )
    # We also update the existing row to use the old default.
    op.execute(
        f"UPDATE global_settings SET tool_prompts_default = '{old_prompts_sql_safe}'::jsonb WHERE id = 1"
    )