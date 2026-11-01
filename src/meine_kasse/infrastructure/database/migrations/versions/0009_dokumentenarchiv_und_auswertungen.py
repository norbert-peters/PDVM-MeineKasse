"""Dokumentenarchiv und gespeicherte Auswertungen

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('TABLE', 'REPORT')", name=op.f("ck_documents_document_type_valid")
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_documents_size_valid")),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name=op.f("fk_documents_created_by_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("file_name", name=op.f("uq_documents_file_name")),
    )
    op.create_index(
        op.f("ix_documents_created_by_user_id"), "documents", ["created_by_user_id"], unique=False
    )

    op.create_table(
        "report_definitions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("data_source", sa.String(length=30), nullable=False),
        sa.Column("columns_json", sa.Text(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column("sort_json", sa.Text(), nullable=False),
        sa.Column("grouping_json", sa.Text(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "data_source IN ('BOOKINGS', 'PLAN_ACTUAL', 'ACCOUNTS')",
            name=op.f("ck_report_definitions_data_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_report_definitions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_definitions")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_report_definitions_user_id")),
    )
    op.create_index(
        op.f("ix_report_definitions_user_id"), "report_definitions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_report_definitions_user_id"), table_name="report_definitions")
    op.drop_table("report_definitions")
    op.drop_index(op.f("ix_documents_created_by_user_id"), table_name="documents")
    op.drop_table("documents")
