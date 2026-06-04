"""Initial Postgres schema aligned with polaris SQLite."""

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
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False, server_default=""),
        sa.Column("stage", sa.String(64), server_default="initial"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(128), nullable=True),
    )
    op.create_table(
        "experiment_data",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.BigInteger(), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "conversation_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(64), nullable=True),
        sa.Column("prompt_session_id", sa.String(64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("conversation_events")
    op.drop_table("experiment_data")
    op.drop_table("app_config")
    op.drop_table("experiments")
    op.drop_table("users")
