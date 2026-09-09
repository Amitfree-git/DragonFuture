"""Preserve partial OHLC without fabricating traded prices."""
from alembic import op
import sqlalchemy as sa
revision = 'e7b0f3a2c468'
down_revision = 'd6a9e2f1b357'
branch_labels = None
depends_on = None
FIELDS = ('open_price', 'high_price', 'low_price', 'close_price')
def upgrade():
    with op.batch_alter_table('fut_bar_daily') as batch:
        for field in FIELDS:
            batch.alter_column(field, existing_type=sa.Numeric(24, 8), nullable=True)
def downgrade():
    condition = ' OR '.join(field + ' IS NULL' for field in FIELDS)
    if op.get_bind().execute(sa.text('SELECT 1 FROM fut_bar_daily WHERE ' + condition + ' LIMIT 1')).first():
        raise RuntimeError('Cannot downgrade: partial OHLC records must be preserved.')
    with op.batch_alter_table('fut_bar_daily') as batch:
        for field in FIELDS:
            batch.alter_column(field, existing_type=sa.Numeric(24, 8), nullable=False)
