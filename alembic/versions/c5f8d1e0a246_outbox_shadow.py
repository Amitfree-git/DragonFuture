"""outbox and shadow run tables

Revision ID: c5f8d1e0a246
Revises: b4e7c2a9d013
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5f8d1e0a246"
down_revision: Union[str, None] = "b4e7c2a9d013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fut_event_outbox",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fut_event_outbox_status", "fut_event_outbox", ["status", "available_at"])
    op.create_table(
        "fut_shadow_run",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("watermark_status", sa.String(length=32), nullable=False),
        sa.Column("input_data_hash", sa.String(length=64), nullable=True),
        sa.Column("core_result_hash", sa.String(length=64), nullable=True),
        sa.Column("opportunity_action", sa.String(length=32), nullable=True),
        sa.Column("hard_gate", sa.Boolean(), nullable=False),
        sa.Column("gap", sa.Boolean(), nullable=False),
        sa.Column("candidate_emitted", sa.Boolean(), nullable=False),
        sa.Column("blocking_reasons", sa.JSON(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("exchange", "symbol", "session_date", "horizon", name="uq_fut_shadow_run_session"),
    )


def downgrade() -> None:
    op.drop_table("fut_shadow_run")
    op.drop_index("ix_fut_event_outbox_status", table_name="fut_event_outbox")
    op.drop_table("fut_event_outbox")
