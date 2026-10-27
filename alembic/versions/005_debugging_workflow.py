"""Add durable automated debugging workflow records."""

from alembic import op
import sqlalchemy as sa


revision = "005_debugging_workflow"
down_revision = "004_controlled_execution"
branch_labels = None
depends_on = None


def _json():
    return sa.JSON()


def upgrade() -> None:
    op.add_column("execution_runs", sa.Column("source_override_path", sa.Text(), nullable=True))

    op.create_table(
        "debug_investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_trace_id", sa.String(128), nullable=False),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_revision", sa.String(200), nullable=True),
        sa.Column("archive_fingerprint", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_category", sa.String(64), nullable=False),
        sa.Column("failure_summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", _json(), nullable=False),
        sa.Column("missing_evidence_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_debug_investigations_project_id", "debug_investigations", ["project_id"])
    op.create_index("ix_debug_investigations_project_created", "debug_investigations", ["project_id", "created_at"])
    op.create_index("ix_debug_investigations_project_status", "debug_investigations", ["project_id", "status"])
    op.create_index("ix_debug_investigations_original_trace_id", "debug_investigations", ["original_trace_id"])
    op.create_index("ix_debug_investigations_original_execution_id", "debug_investigations", ["original_execution_id"])
    op.create_index("ix_debug_investigations_analysis_id", "debug_investigations", ["analysis_id"])

    op.create_table(
        "root_cause_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("debug_investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("source_revision", sa.String(200), nullable=True),
        sa.Column("source_file_path", sa.String(500), nullable=True),
        sa.Column("source_start_line", sa.Integer(), nullable=True),
        sa.Column("source_end_line", sa.Integer(), nullable=True),
        sa.Column("trace_event_ids", _json(), nullable=False),
        sa.Column("supporting_evidence", _json(), nullable=False),
        sa.Column("contradictory_evidence", _json(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("evidence_kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_root_cause_candidates_investigation_id", "root_cause_candidates", ["investigation_id"])
    op.create_index("ix_root_cause_candidates_investigation_rank", "root_cause_candidates", ["investigation_id", "rank"])

    op.create_table(
        "reproduction_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("debug_investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reproduction_execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_trace_id", sa.String(128), nullable=False),
        sa.Column("reproduction_trace_id", sa.String(128), nullable=True),
        sa.Column("source_revision", sa.String(200), nullable=True),
        sa.Column("input_json", _json(), nullable=False),
        sa.Column("input_provenance_json", _json(), nullable=False),
        sa.Column("configuration_json", _json(), nullable=False),
        sa.Column("environment_json", _json(), nullable=False),
        sa.Column("differences_json", _json(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("signature_match", sa.Boolean(), nullable=True),
        sa.Column("result_json", _json(), nullable=False),
        sa.Column("logs_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_reproduction_attempts_investigation_id", "reproduction_attempts", ["investigation_id"])
    op.create_index("ix_reproduction_attempts_reproduction_execution_id", "reproduction_attempts", ["reproduction_execution_id"])
    op.create_index("ix_reproduction_attempts_investigation_created", "reproduction_attempts", ["investigation_id", "created_at"])

    op.create_table(
        "regression_test_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("debug_investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("root_cause_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_revision", sa.String(200), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_json", _json(), nullable=False),
        sa.Column("expected_json", _json(), nullable=False),
        sa.Column("source_evidence_json", _json(), nullable=False),
        sa.Column("assumptions_json", _json(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("original_result_json", _json(), nullable=False),
        sa.Column("patched_result_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_regression_test_artifacts_investigation_id", "regression_test_artifacts", ["investigation_id"])
    op.create_index("ix_regression_test_artifacts_investigation_created", "regression_test_artifacts", ["investigation_id", "created_at"])

    op.create_table(
        "proposed_patches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("debug_investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("root_cause_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("regression_test_id", sa.String(36), sa.ForeignKey("regression_test_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("base_source_revision", sa.String(200), nullable=True),
        sa.Column("base_archive_fingerprint", sa.String(64), nullable=True),
        sa.Column("patch_text", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_json", _json(), nullable=False),
        sa.Column("change_json", _json(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_proposed_patches_investigation_id", "proposed_patches", ["investigation_id"])
    op.create_index("ix_proposed_patches_investigation_created", "proposed_patches", ["investigation_id", "created_at"])

    op.create_table(
        "verification_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("debug_investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patch_id", sa.String(36), sa.ForeignKey("proposed_patches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("regression_test_id", sa.String(36), sa.ForeignKey("regression_test_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patched_execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_trace_id", sa.String(128), nullable=False),
        sa.Column("patched_trace_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("original_test_json", _json(), nullable=False),
        sa.Column("patched_test_json", _json(), nullable=False),
        sa.Column("existing_tests_json", _json(), nullable=False),
        sa.Column("command_results_json", _json(), nullable=False),
        sa.Column("report_json", _json(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_verification_runs_investigation_id", "verification_runs", ["investigation_id"])
    op.create_index("ix_verification_runs_patch_id", "verification_runs", ["patch_id"])
    op.create_index("ix_verification_runs_regression_test_id", "verification_runs", ["regression_test_id"])
    op.create_index("ix_verification_runs_investigation_created", "verification_runs", ["investigation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("verification_runs")
    op.drop_table("proposed_patches")
    op.drop_table("regression_test_artifacts")
    op.drop_table("reproduction_attempts")
    op.drop_table("root_cause_candidates")
    op.drop_table("debug_investigations")
    op.drop_column("execution_runs", "source_override_path")
