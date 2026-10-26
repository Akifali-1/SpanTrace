"""Add durable controlled execution records."""

from alembic import op
import sqlalchemy as sa


revision = "004_controlled_execution"
down_revision = "003_repository_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("configuration_id", sa.String(36), sa.ForeignKey("instrumentation_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_revision", sa.String(200), nullable=False),
        sa.Column("archive_fingerprint", sa.String(64), nullable=False),
        sa.Column("entry_finding_id", sa.String(64), nullable=False),
        sa.Column("entry_file_path", sa.String(500), nullable=False),
        sa.Column("entry_symbol", sa.String(240), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("worker_container_id", sa.String(128)),
        sa.Column("execution_token_hash", sa.String(64), nullable=False),
        sa.Column("execution_token_prefix", sa.String(16), nullable=False),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("failure_category", sa.String(64)),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("logs_text", sa.Text(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("cpu_limit", sa.String(32), nullable=False),
        sa.Column("pids_limit", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("cancel_requested_at", sa.DateTime()),
        sa.UniqueConstraint("trace_id", name="uq_execution_trace_id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_execution_project_idempotency"),
    )
    op.create_index("ix_execution_runs_project_id", "execution_runs", ["project_id"])
    op.create_index("ix_execution_runs_analysis_id", "execution_runs", ["analysis_id"])
    op.create_index("ix_execution_runs_configuration_id", "execution_runs", ["configuration_id"])
    op.create_index("ix_execution_runs_trace_id", "execution_runs", ["trace_id"])
    op.create_index("ix_execution_runs_project_created", "execution_runs", ["project_id", "created_at"])
    op.create_index("ix_execution_runs_project_status", "execution_runs", ["project_id", "status"])


def downgrade() -> None:
    op.drop_table("execution_runs")
