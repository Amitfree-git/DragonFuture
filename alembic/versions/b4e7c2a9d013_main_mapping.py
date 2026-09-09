"""main contract mapping and series snapshot vintage

Revision ID: b4e7c2a9d013
Revises: a1c0e9f3b812
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4e7c2a9d013"
down_revision: Union[str, None] = "a1c0e9f3b812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fut_series_snapshot",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("series_type", sa.String(length=32), nullable=False),
        sa.Column("calculation_version", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["fut_instrument.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "instrument_id",
            "series_type",
            "calculation_version",
            "input_hash",
            name="uq_fut_series_snapshot_identity",
        ),
    )
    op.create_table(
        "fut_active_contract_mapping",
        sa.Column("mapping_id", sa.String(length=64), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("from_contract_id", sa.Integer(), nullable=True),
        sa.Column("to_contract_id", sa.Integer(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("effective_session", sa.Date(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("challenger_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["fut_instrument.instrument_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["from_contract_id"], ["fut_contract.contract_id"]),
        sa.ForeignKeyConstraint(["to_contract_id"], ["fut_contract.contract_id"]),
        sa.UniqueConstraint(
            "instrument_id",
            "decision_date",
            "policy_version",
            name="uq_fut_active_contract_mapping_decision",
        ),
    )
    op.create_index(
        "ix_fut_mapping_effective",
        "fut_active_contract_mapping",
        ["instrument_id", "effective_session"],
    )
    with op.batch_alter_table("fut_continuous_bar_daily") as batch_op:
        batch_op.add_column(sa.Column("series_snapshot_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_fut_continuous_bar_daily_series_snapshot_id_fut_series_snapshot"),
            "fut_series_snapshot",
            ["series_snapshot_id"],
            ["snapshot_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("fut_continuous_bar_daily") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_fut_continuous_bar_daily_series_snapshot_id_fut_series_snapshot"),
            type_="foreignkey",
        )
        batch_op.drop_column("series_snapshot_id")
    op.drop_index("ix_fut_mapping_effective", table_name="fut_active_contract_mapping")
    op.drop_table("fut_active_contract_mapping")
    op.drop_table("fut_series_snapshot")
