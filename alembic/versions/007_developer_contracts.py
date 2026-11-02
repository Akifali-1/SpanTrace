"""Add developer-defined contracts and execution results."""

from alembic import op
import sqlalchemy as sa


revision = "007_developer_contracts"
down_revision = "006_patch_approval_audit"
branch_labels = None
depends_on = None


def _json():
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("record_id", sa.String(36), primary_key=True),
        sa.Column("id", sa.String(200), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_analysis_id", sa.String(36), sa.ForeignKey("repository_analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("predicate", sa.String(48), nullable=False),
        sa.Column("arguments_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "id", "version", name="uq_contract_project_id_version"),
    )
    op.create_index("ix_contracts_project_id", "contracts", ["project_id"])
    op.create_index("ix_contracts_source_analysis_id", "contracts", ["source_analysis_id"])
    op.create_index("ix_contracts_status", "contracts", ["status"])
    op.create_index("ix_contracts_project_status", "contracts", ["project_id", "status"])

    op.create_table(
        "contract_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_record_id", sa.String(36), sa.ForeignKey("contracts.record_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details_json", _json(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("execution_id", "contract_record_id", name="uq_contract_result_execution_contract"),
    )
    op.create_index("ix_contract_results_execution_id", "contract_results", ["execution_id"])
    op.create_index("ix_contract_results_contract_record_id", "contract_results", ["contract_record_id"])
    op.add_column("regression_test_artifacts", sa.Column("contract_record_id", sa.String(36), sa.ForeignKey("contracts.record_id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_regression_test_artifacts_contract_record_id", "regression_test_artifacts", ["contract_record_id"])


def downgrade() -> None:
    op.drop_index("ix_regression_test_artifacts_contract_record_id", table_name="regression_test_artifacts")
    op.drop_column("regression_test_artifacts", "contract_record_id")
    op.drop_table("contract_results")
    op.drop_table("contracts")
