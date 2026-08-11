"""Add versioned network access to scripts."""

import sqlalchemy as sa

from alembic import op

revision = "20260803_08"
down_revision = "20260803_07"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "network_enabled" not in _columns("script_versions"):
        op.add_column(
            "script_versions",
            sa.Column(
                "network_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if "network_enabled" in _columns("script_versions"):
        op.drop_column("script_versions", "network_enabled")
