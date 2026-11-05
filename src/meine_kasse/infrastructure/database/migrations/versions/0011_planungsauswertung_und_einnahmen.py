"""Kostenstellen in der Planungsauswertung und Datenquelle Einnahmen

Neue Spalte `always_in_plan_report` der Kostenstellen (nicht bei Einnahmen) und die Datenquelle
`INCOME` für gespeicherte Auswertungen. Bestehende Daten bleiben unverändert.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-04 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cost_centers") as batch:
        batch.add_column(
            sa.Column(
                "always_in_plan_report", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.create_check_constraint(
            "plan_report_not_for_income", "NOT always_in_plan_report OR kind <> 'INCOME'"
        )
    with op.batch_alter_table("report_definitions") as batch:
        batch.drop_constraint("data_source_valid", type_="check")
        batch.create_check_constraint(
            "data_source_valid", "data_source IN ('BOOKINGS', 'PLAN_ACTUAL', 'ACCOUNTS', 'INCOME')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM report_definitions WHERE data_source = 'INCOME'")
    with op.batch_alter_table("report_definitions") as batch:
        batch.drop_constraint("data_source_valid", type_="check")
        batch.create_check_constraint(
            "data_source_valid", "data_source IN ('BOOKINGS', 'PLAN_ACTUAL', 'ACCOUNTS')"
        )
    with op.batch_alter_table("cost_centers") as batch:
        batch.drop_constraint("plan_report_not_for_income", type_="check")
        batch.drop_column("always_in_plan_report")
