"""initial AgentScope schema"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("projects", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("api_keys", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("key_hash", sa.String(64), nullable=False, unique=True), sa.Column("prefix", sa.String(16), nullable=False), sa.Column("revoked_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_table("runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("trace_id", sa.String(128), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("ended_at", sa.DateTime()), sa.Column("duration_ms", sa.Integer()), sa.Column("event_count", sa.Integer(), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.UniqueConstraint("project_id", "trace_id", name="uq_project_trace"))
    op.create_index("ix_runs_project_id", "runs", ["project_id"])
    op.create_index("ix_runs_trace_id", "runs", ["trace_id"])
    op.create_table("trace_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False), sa.Column("event_id", sa.String(128), nullable=False), sa.Column("span_id", sa.String(128)), sa.Column("parent_span_id", sa.String(128)), sa.Column("agent_name", sa.String(160)), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("kind", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("occurred_at", sa.DateTime(), nullable=False), sa.Column("ended_at", sa.DateTime()), sa.Column("duration_ms", sa.Integer()), sa.Column("input_json", sa.JSON()), sa.Column("output_json", sa.JSON()), sa.Column("tool_name", sa.String(160)), sa.Column("tool_args", sa.JSON()), sa.Column("tool_result", sa.JSON()), sa.Column("handoff_to", sa.String(160)), sa.Column("error_type", sa.String(160)), sa.Column("error_details", sa.Text()), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("schema_version", sa.String(16), nullable=False), sa.UniqueConstraint("project_id", "event_id", name="uq_project_event"))
    op.create_index("ix_trace_events_project_id", "trace_events", ["project_id"])
    op.create_index("ix_trace_events_run_id", "trace_events", ["run_id"])
    op.create_index("ix_trace_events_occurred_at", "trace_events", ["occurred_at"])
    op.create_table("regression_cases", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("source_trace_id", sa.String(128), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("scenario", sa.JSON(), nullable=False), sa.Column("expected_assertions", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_regression_cases_project_id", "regression_cases", ["project_id"])
    op.create_table("regression_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("case_id", sa.String(36), sa.ForeignKey("regression_cases.id", ondelete="CASCADE"), nullable=False), sa.Column("passed", sa.Boolean(), nullable=False), sa.Column("actual", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_regression_runs_case_id", "regression_runs", ["case_id"])


def downgrade() -> None:
    op.drop_table("regression_runs")
    op.drop_table("regression_cases")
    op.drop_table("trace_events")
    op.drop_table("runs")
    op.drop_table("api_keys")
    op.drop_table("projects")
