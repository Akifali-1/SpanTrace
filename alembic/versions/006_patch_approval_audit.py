"""Record patch approval actor and timestamp."""

from alembic import op
import sqlalchemy as sa


revision = "006_patch_approval_audit"
down_revision = "005_debugging_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposed_patches", sa.Column("approved_by", sa.String(120), nullable=True))
    op.add_column("proposed_patches", sa.Column("approved_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposed_patches", "approved_at")
    op.drop_column("proposed_patches", "approved_by")
