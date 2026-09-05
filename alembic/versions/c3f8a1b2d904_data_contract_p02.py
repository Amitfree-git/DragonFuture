"""data contract schema: calendar, manifest, timestamps

Revision ID: c3f8a1b2d904
Revises: d5ad33d0aea4
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3f8a1b2d904"
down_revision: Union[str, None] = "d5ad33d0aea4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fut_data_manifest",
        sa.Column("manifest_id", sa.String(length=64), nullable=False),
        sa.Column("source_policy", sa.String(length=64), nullable=False),
        sa.Column("data_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("max_available_at", sa.DateTime(), nullable=True),
        sa.Column("record_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("manifest_id", name=op.f("pk_fut_data_manifest")),
    )
    op.create_table(
        "fut_raw_archive",
        sa.Column("archive_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("license_id", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("archive_id", name=op.f("pk_fut_raw_archive")),
        sa.UniqueConstraint(
            "provider", "request_digest", "response_hash",
            name="uq_fut_raw_archive_payload",
        ),
    )
    op.create_table(
        "fut_calendar_day",
        sa.Column("day_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("day_id", name=op.f("pk_fut_calendar_day")),
        sa.UniqueConstraint(
            "exchange", "version", "trading_date", "revision_no",
            name="uq_fut_calendar_day_revision",
        ),
    )
    op.create_index(
        "ix_fut_calendar_day_pit",
        "fut_calendar_day",
        ["exchange", "trading_date", "available_at"],
        unique=False,
    )
    with op.batch_alter_table("fut_data_batch") as batch_op:
        batch_op.add_column(sa.Column("manifest_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_fut_data_batch_manifest_id_fut_data_manifest"),
            "fut_data_manifest",
            ["manifest_id"],
            ["manifest_id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("fut_bar_daily") as batch_op:
        batch_op.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("received_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("data_mode", sa.String(length=32), nullable=True))
    with op.batch_alter_table("fut_contract") as batch_op:
        batch_op.add_column(sa.Column("tradable_until", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("account_eligibility", sa.String(length=32), nullable=True))
    with op.batch_alter_table("fut_contract_spec") as batch_op:
        batch_op.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("available_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("fut_contract_spec") as batch_op:
        batch_op.drop_column("revision_no")
        batch_op.drop_column("source")
        batch_op.drop_column("available_at")
        batch_op.drop_column("published_at")
    with op.batch_alter_table("fut_contract") as batch_op:
        batch_op.drop_column("account_eligibility")
        batch_op.drop_column("tradable_until")
    with op.batch_alter_table("fut_bar_daily") as batch_op:
        batch_op.drop_column("data_mode")
        batch_op.drop_column("received_at")
        batch_op.drop_column("published_at")
    with op.batch_alter_table("fut_data_batch") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_fut_data_batch_manifest_id_fut_data_manifest"),
            type_="foreignkey",
        )
        batch_op.drop_column("manifest_id")
    op.drop_index("ix_fut_calendar_day_pit", table_name="fut_calendar_day")
    op.drop_table("fut_calendar_day")
    op.drop_table("fut_raw_archive")
    op.drop_table("fut_data_manifest")
