"""Add repository import, discovery, and instrumentation configuration tables."""

from alembic import op
import sqlalchemy as sa


revision = "003_repository_intelligence"
down_revision = "002_instrumentation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(500)),
        sa.Column("branch", sa.String(200)),
        sa.Column("commit_sha", sa.String(128)),
        sa.Column("source_revision", sa.String(200), nullable=False),
        sa.Column("archive_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime()),
    )
    op.create_index("ix_repository_analyses_project_id", "repository_analyses", ["project_id"])
    op.create_index("ix_repository_analyses_archive_fingerprint", "repository_analyses", ["archive_fingerprint"])
    op.create_index("ix_repository_analyses_project_created", "repository_analyses", ["project_id", "created_at"])

    op.create_table(
        "repository_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stable_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("symbol_type", sa.String(64)),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("symbol_name", sa.String(240)),
        sa.Column("framework", sa.String(120)),
        sa.Column("detection_method", sa.String(160), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(48), nullable=False),
        sa.Column("instrumentation_status", sa.String(48), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("analysis_id", "stable_id", name="uq_repository_finding_stable"),
    )
    op.create_index("ix_repository_findings_analysis_id", "repository_findings", ["analysis_id"])
    op.create_index("ix_repository_findings_analysis_kind", "repository_findings", ["analysis_id", "kind"])

    op.create_table(
        "repository_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_finding_id", sa.String(36), sa.ForeignKey("repository_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_finding_id", sa.String(36), sa.ForeignKey("repository_findings.id", ondelete="CASCADE")),
        sa.Column("target_name", sa.String(240)),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("confidence", sa.String(48), nullable=False),
        sa.Column("detection_method", sa.String(160), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_repository_relationships_analysis_id", "repository_relationships", ["analysis_id"])
    op.create_index("ix_repository_relationships_source_finding_id", "repository_relationships", ["source_finding_id"])
    op.create_index("ix_repository_relationships_target_finding_id", "repository_relationships", ["target_finding_id"])

    op.create_table(
        "instrumentation_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("analysis_id", "version", name="uq_instrumentation_config_version"),
    )
    op.create_index("ix_instrumentation_configs_project_id", "instrumentation_configs", ["project_id"])
    op.create_index("ix_instrumentation_configs_analysis_id", "instrumentation_configs", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("instrumentation_configs")
    op.drop_table("repository_relationships")
    op.drop_table("repository_findings")
    op.drop_table("repository_analyses")
