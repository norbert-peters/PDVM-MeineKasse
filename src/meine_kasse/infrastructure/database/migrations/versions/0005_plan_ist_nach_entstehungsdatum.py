"""Plan-Ist nach Entstehungsdatum

Die Ist-Werte der Kostenstellen (monthly_actuals) werden ab jetzt in der Planperiode des
Entstehungsdatums geführt (Architekturvorgabe 2.11). Diese Migration baut sie aus den
vorhandenen Buchungen neu auf. Das Schema ändert sich nicht.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 12:00:00.000000
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTUALS = sa.table(
    'monthly_actuals',
    sa.column('id', sa.String),
    sa.column('name', sa.String),
    sa.column('cost_center_id', sa.String),
    sa.column('year', sa.Integer),
    sa.column('month', sa.Integer),
    sa.column('debit_cents', sa.Integer),
    sa.column('credit_cents', sa.Integer),
    sa.column('reserve_actual_cents', sa.Integer),
    sa.column('created_at', sa.DateTime),
    sa.column('updated_at', sa.DateTime),
)

_TOTALS = sa.text(
    """
    SELECT l.cost_center_id,
           CAST(strftime('%Y', b.origin_date) AS INTEGER),
           CAST(strftime('%m', b.origin_date) AS INTEGER),
           l.side,
           SUM(b.amount_cents)
    FROM booking_legs l
    JOIN bookings b ON b.id = l.booking_id
    WHERE l.cost_center_id IS NOT NULL AND b.booking_type != 'BUDGET_TRANSFER'
    GROUP BY 1, 2, 3, 4
    """
)


def _rebuild_actuals() -> None:
    bind = op.get_bind()
    totals: dict[tuple[str, int, int], list[int]] = defaultdict(lambda: [0, 0])
    for cost_center_id, year, month, side, amount in bind.execute(_TOTALS):
        totals[(cost_center_id, year, month)][0 if side == 'DEBIT' else 1] += int(amount)

    existing = {
        (row.cost_center_id, row.year, row.month)
        for row in bind.execute(sa.select(_ACTUALS.c.cost_center_id, _ACTUALS.c.year, _ACTUALS.c.month))
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    bind.execute(sa.update(_ACTUALS).values(debit_cents=0, credit_cents=0))
    for (cost_center_id, year, month), (debit, credit) in totals.items():
        if (cost_center_id, year, month) in existing:
            bind.execute(
                sa.update(_ACTUALS)
                .where(
                    _ACTUALS.c.cost_center_id == cost_center_id,
                    _ACTUALS.c.year == year,
                    _ACTUALS.c.month == month,
                )
                .values(debit_cents=debit, credit_cents=credit)
            )
        else:
            bind.execute(
                sa.insert(_ACTUALS).values(
                    id=str(uuid.uuid4()),
                    name='',
                    cost_center_id=cost_center_id,
                    year=year,
                    month=month,
                    debit_cents=debit,
                    credit_cents=credit,
                    reserve_actual_cents=0,
                    created_at=now,
                    updated_at=now,
                )
            )


def upgrade() -> None:
    _rebuild_actuals()


def downgrade() -> None:
    # Die Summen nach Buchungsdatum lassen sich aus den Buchungen nicht ohne Weiteres
    # wiederherstellen; der Neuaufbau über die Anwendung bleibt gültig.
    pass
