"""curve snapshot batch identity

Revision ID: a1c0e9f3b812
Revises: c3f8a1b2d904
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1c0e9f3b812"
down_revision: Union[str, None] = "c3f8a1b2d904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("fut_curve_snapshot") as batch_op:
        batch_op.add_column(sa.Column("data_batch_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_fut_curve_snapshot_data_batch_id_fut_data_batch"),
            "fut_data_batch",
            ["data_batch_id"],
            ["batch_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("fut_curve_snapshot") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_fut_curve_snapshot_data_batch_id_fut_data_batch"),
            type_="foreignkey",
        )
        batch_op.drop_column("data_batch_id")
