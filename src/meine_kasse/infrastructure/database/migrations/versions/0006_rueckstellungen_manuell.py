"""Rückstellungen: Kennzeichnung manueller Zuführungen

Bisher von Hand erfasste Zuführungen (reserve_plan_cents > 0) bleiben erhalten und gelten als
manuell. Die maschinelle Verteilung überschreibt sie nicht. Die Entlastung und der Vortrag werden
beim Start der Anwendung aus Plan und Ist neu berechnet.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'monthly_plans',
        sa.Column('reserve_is_manual', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute('UPDATE monthly_plans SET reserve_is_manual = 1 WHERE reserve_plan_cents > 0')


def downgrade() -> None:
    with op.batch_alter_table('monthly_plans') as batch:
        batch.drop_column('reserve_is_manual')
