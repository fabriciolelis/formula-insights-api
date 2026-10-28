"""Identify race results by car number, so a driver can have two cars in one race.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Batch mode, because SQLite cannot drop a constraint in place.
    with op.batch_alter_table('race_results') as batch_op:
        batch_op.add_column(sa.Column('number', sa.String(length=10), nullable=True))
        batch_op.drop_constraint('uq_result_race_driver', type_='unique')
        batch_op.create_unique_constraint(
            'uq_result_race_driver_number', ['race_id', 'driver_id', 'number']
        )


def downgrade() -> None:
    """Downgrade schema (generated; not relied on, see ADR-007)."""
    with op.batch_alter_table('race_results') as batch_op:
        batch_op.drop_constraint('uq_result_race_driver_number', type_='unique')
        batch_op.create_unique_constraint('uq_result_race_driver', ['race_id', 'driver_id'])
        batch_op.drop_column('number')
