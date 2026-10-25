"""Add integration and relationship fields for automatic instrumentation."""

from alembic import op
import sqlalchemy as sa


revision = "002_instrumentation_fields"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trace_events", sa.Column("model_name", sa.String(160), nullable=True))
    op.add_column("trace_events", sa.Column("integration", sa.String(80), nullable=False, server_default="manual"))
    op.add_column("trace_events", sa.Column("framework", sa.String(120), nullable=True))
    op.add_column("trace_events", sa.Column("framework_run_id", sa.String(160), nullable=True))
    op.add_column("trace_events", sa.Column("framework_parent_id", sa.String(160), nullable=True))
    op.add_column("trace_events", sa.Column("relationship", sa.String(64), nullable=False, server_default="observed"))
    op.add_column("trace_events", sa.Column("relationship_confidence", sa.String(32), nullable=False, server_default="observed"))


def downgrade() -> None:
    op.drop_column("trace_events", "relationship_confidence")
    op.drop_column("trace_events", "relationship")
    op.drop_column("trace_events", "framework_parent_id")
    op.drop_column("trace_events", "framework_run_id")
    op.drop_column("trace_events", "framework")
    op.drop_column("trace_events", "integration")
    op.drop_column("trace_events", "model_name")
