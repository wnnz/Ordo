"""Add workflow folders."""

import sqlalchemy as sa

from alembic import op

revision = "20260914_10"
down_revision = "20260812_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_folders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workflow_folders_workspace_name"),
    )
    op.create_index(
        "ix_workflow_folders_workspace_id", "workflow_folders", ["workspace_id"]
    )
    op.add_column("workflows", sa.Column("folder_id", sa.String(length=36), nullable=True))
    op.create_index("ix_workflows_folder_id", "workflows", ["folder_id"])
    op.create_foreign_key(
        "fk_workflows_folder_id_workflow_folders",
        "workflows",
        "workflow_folders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workflows_folder_id_workflow_folders", "workflows", type_="foreignkey"
    )
    op.drop_index("ix_workflows_folder_id", table_name="workflows")
    op.drop_column("workflows", "folder_id")
    op.drop_index("ix_workflow_folders_workspace_id", table_name="workflow_folders")
    op.drop_table("workflow_folders")
