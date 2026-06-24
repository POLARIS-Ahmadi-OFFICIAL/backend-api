"""Initial schema — all 14 tables."""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_int", sa.BigInteger(), nullable=True),
        sa.Column("value_real", sa.Float(), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "experimental_constraints",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("techniques_json", sa.Text(), nullable=True),
        sa.Column("equipment_json", sa.Text(), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("focus_areas_json", sa.Text(), nullable=True),
        sa.Column("liquid_handling_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "jupyter_config",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("server_url", sa.Text(), nullable=True),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("upload_enabled", sa.Integer(), nullable=True),
        sa.Column("notebook_path", sa.Text(), nullable=True),
    )
    op.create_table(
        "experiment_data",
        sa.Column("experiment_id", sa.BigInteger(), sa.ForeignKey("experiments.id"), primary_key=True),
        sa.Column("state_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "conversation_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("prompt_session_id", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "agent_usage_counts",
        sa.Column("agent_name", sa.String(128), primary_key=True),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "workflows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("ml_model_choice", sa.Text(), nullable=True),
    )
    op.create_table(
        "workflow_steps",
        sa.Column("workflow_id", sa.BigInteger(), sa.ForeignKey("workflows.id"), nullable=False),
        sa.Column("step_order", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("automatic", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("workflow_id", "step_order"),
    )
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
    )
    op.create_table(
        "session_state",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("state_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "negative_hypotheses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("analysis_summary", sa.Text(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hypothesis_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_text", sa.Text(), nullable=False),
        sa.Column("material_hint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "hypothesis_outcomes", "negative_hypotheses", "session_state",
        "uploaded_files", "workflow_steps", "workflows", "agent_usage_counts",
        "conversation_events", "experiment_data", "jupyter_config",
        "experimental_constraints", "app_config", "experiments", "users",
    ]:
        op.drop_table(table)
