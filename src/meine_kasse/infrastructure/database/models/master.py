from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.domain.enums import AccountType, ClosureKind, CostCenterKind, IncomeMode
from meine_kasse.infrastructure.database.base import Base, UtcDateTime
from meine_kasse.infrastructure.database.models.mixins import (
    IdNameMixin,
    TimestampMixin,
    in_values,
)


class UserModel(IdNameMixin, TimestampMixin, Base):
    """`name` ist der Anmeldename. Es wird nur der Hash des Passworts gespeichert."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("name"),)

    last_name: Mapped[str] = mapped_column(String(100), default="")
    first_name: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    initial_password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CostCenterModel(IdNameMixin, TimestampMixin, Base):
    __tablename__ = "cost_centers"
    __table_args__ = (
        UniqueConstraint("number"),
        CheckConstraint(in_values("kind", CostCenterKind), name="kind_valid"),
        CheckConstraint(
            "income_mode IS NULL OR " + in_values("income_mode", IncomeMode),
            name="income_mode_valid",
        ),
        CheckConstraint(
            "(kind = 'INCOME') = (income_mode IS NOT NULL)", name="income_mode_matches_kind"
        ),
        CheckConstraint(
            "NOT always_in_plan_report OR kind <> 'INCOME'", name="plan_report_not_for_income"
        ),
    )

    number: Mapped[str] = mapped_column(String(20))
    valid_from: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), default=CostCenterKind.STANDARD.value)
    income_mode: Mapped[str | None] = mapped_column(String(10), default=None)
    always_in_plan_report: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccountModel(IdNameMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("number"),
        CheckConstraint(in_values("account_type", AccountType), name="account_type_valid"),
    )

    number: Mapped[str] = mapped_column(String(20))
    account_type: Mapped[str] = mapped_column(String(20))
    bank_name: Mapped[str] = mapped_column(String(200), default="")
    owner_name: Mapped[str] = mapped_column(String(200), default="")
    iban: Mapped[str | None] = mapped_column(String(34), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BookingControlModel(IdNameMixin, TimestampMixin, Base):
    """Buchungssteuerung. Es gibt genau einen aktiven Datensatz."""

    __tablename__ = "booking_control"
    __table_args__ = (
        CheckConstraint("current_month BETWEEN 1 AND 12", name="current_month_valid"),
        CheckConstraint(
            "last_closed_month IS NULL OR last_closed_month BETWEEN 1 AND 12",
            name="last_closed_month_valid",
        ),
        Index(
            "uq_booking_control_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    planning_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    current_year: Mapped[int] = mapped_column(Integer)
    current_month: Mapped[int] = mapped_column(Integer)
    last_closed_year: Mapped[int | None] = mapped_column(Integer, default=None)
    last_closed_month: Mapped[int | None] = mapped_column(Integer, default=None)


class PeriodClosureModel(IdNameMixin, TimestampMixin, Base):
    __tablename__ = "period_closures"
    __table_args__ = (
        UniqueConstraint("year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_valid"),
    )

    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    closed_on: Mapped[date] = mapped_column(Date)
    closed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    signature: Mapped[str] = mapped_column(String(64))


class YearClosureModel(IdNameMixin, TimestampMixin, Base):
    __tablename__ = "year_closures"
    __table_args__ = (UniqueConstraint("year"),)

    year: Mapped[int] = mapped_column(Integer)
    closed_on: Mapped[date] = mapped_column(Date)
    closed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    signature: Mapped[str] = mapped_column(String(64))


class ClosureReopeningModel(IdNameMixin, TimestampMixin, Base):
    """Nachweis über das Wiedereröffnen eines Monats- oder Jahresabschlusses (nie gelöscht)."""

    __tablename__ = "closure_reopenings"
    __table_args__ = (
        CheckConstraint(in_values("kind", ClosureKind), name="kind_valid"),
        CheckConstraint(
            "(kind = 'MONTH' AND month BETWEEN 1 AND 12) OR (kind = 'YEAR' AND month IS NULL)",
            name="month_matches_kind",
        ),
    )

    kind: Mapped[str] = mapped_column(String(10))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int | None] = mapped_column(Integer, default=None)
    reopened_on: Mapped[date] = mapped_column(Date)
    reopened_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    previous_signature: Mapped[str] = mapped_column(String(64))
    previous_closed_on: Mapped[date] = mapped_column(Date)
    previous_closed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    signature_was_valid: Mapped[bool] = mapped_column(Boolean)
