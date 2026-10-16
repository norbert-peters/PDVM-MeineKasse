"""Umbuchungen mit Kostenstellen

Eine Umbuchung zwischen Konten besteht aus zwei Buchungssätzen (Kostenstelle → Konto), die über
die gemeinsame GUID `transfer_id` verbunden sind. Bestehende Buchungen bleiben unverändert.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bookings") as batch:
        batch.add_column(sa.Column("transfer_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_bookings_transfer_id", ["transfer_id"])


def downgrade() -> None:
    with op.batch_alter_table("bookings") as batch:
        batch.drop_index("ix_bookings_transfer_id")
        batch.drop_column("transfer_id")
