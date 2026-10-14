"""Einnahmen-Kostenstellen (Art INCOME) mit Verfügbarkeitsmodus

Neue Kostenstellenart `INCOME` und Spalte `income_mode` (`PLAN` oder `ACTUAL`), die genau bei
Einnahmen-Kostenstellen gesetzt ist. Bestehende Kostenstellen bleiben unverändert.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cost_centers") as batch:
        batch.add_column(sa.Column("income_mode", sa.String(length=10), nullable=True))
        batch.drop_constraint("kind_valid", type_="check")
        batch.create_check_constraint(
            "kind_valid", "kind IN ('STANDARD', 'WITHOUT_PLAN', 'INCOME')"
        )
        batch.create_check_constraint(
            "income_mode_valid", "income_mode IS NULL OR income_mode IN ('PLAN', 'ACTUAL')"
        )
        batch.create_check_constraint(
            "income_mode_matches_kind", "(kind = 'INCOME') = (income_mode IS NOT NULL)"
        )


def downgrade() -> None:
    op.execute(
        "UPDATE cost_centers SET kind = 'WITHOUT_PLAN', income_mode = NULL WHERE kind = 'INCOME'"
    )
    with op.batch_alter_table("cost_centers") as batch:
        batch.drop_constraint("income_mode_matches_kind", type_="check")
        batch.drop_constraint("income_mode_valid", type_="check")
        batch.drop_constraint("kind_valid", type_="check")
        batch.create_check_constraint("kind_valid", "kind IN ('STANDARD', 'WITHOUT_PLAN')")
        batch.drop_column("income_mode")
