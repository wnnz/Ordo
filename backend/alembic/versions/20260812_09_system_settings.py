"""Add persistent platform system settings."""

import sqlalchemy as sa

from alembic import op

revision = "20260812_09"
down_revision = "20260803_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "system_settings" in inspector.get_table_names():
        return
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "system_settings" in inspector.get_table_names():
        op.drop_table("system_settings")
