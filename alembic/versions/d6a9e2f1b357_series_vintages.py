"""Immutable causal series payloads and append-only shadow observations.

Revision ID: d6a9e2f1b357
Revises: c5f8d1e0a246
"""
from alembic import op
import sqlalchemy as sa

revision = "d6a9e2f1b357"
down_revision = "c5f8d1e0a246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fut_continuous_bar_daily", sa.Column("research_index", sa.Numeric(38, 18), nullable=True))
    op.add_column("fut_series_snapshot", sa.Column("available_at", sa.DateTime(), nullable=True))
    op.add_column("fut_series_snapshot", sa.Column("payload_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("fut_shadow_run") as batch:
        batch.drop_constraint("uq_fut_shadow_run_session", type_="unique")


def downgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(
        "SELECT 1 FROM fut_shadow_run GROUP BY exchange, symbol, session_date, horizon HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade append-only shadow observations: duplicate sessions must be preserved.")
    with op.batch_alter_table("fut_shadow_run") as batch:
        batch.create_unique_constraint("uq_fut_shadow_run_session", ["exchange", "symbol", "session_date", "horizon"])
    op.drop_column("fut_continuous_bar_daily", "research_index")
    op.drop_column("fut_series_snapshot", "payload_json")
    op.drop_column("fut_series_snapshot", "available_at")
