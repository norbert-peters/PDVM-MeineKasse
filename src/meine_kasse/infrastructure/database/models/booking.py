from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.domain.enums import BookingType, Side
from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import (
    IdNameMixin,
    TimestampMixin,
    in_values,
)


class BookingModel(IdNameMixin, TimestampMixin, Base):
    """Buchungskopf. `amount_cents` ist vorzeichenbehaftet und nie 0."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("amount_cents <> 0", name="amount_not_zero"),
        CheckConstraint(in_values("booking_type", BookingType), name="booking_type_valid"),
        CheckConstraint(in_values("entry_side", Side), name="entry_side_valid"),
        CheckConstraint("fiscal_month BETWEEN 1 AND 12", name="fiscal_month_valid"),
    )

    origin_date: Mapped[date] = mapped_column(Date)
    booking_date: Mapped[date] = mapped_column(Date)
    booking_type: Mapped[str] = mapped_column(String(30))
    entry_side: Mapped[str] = mapped_column(String(6))
    amount_cents: Mapped[int] = mapped_column(Integer)
    merchant: Mapped[str] = mapped_column(String(200), default="")
    booking_text: Mapped[str] = mapped_column(Text, default="")
    reversal_of_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), default=None)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    fiscal_month: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class BookingLegModel(IdNameMixin, TimestampMixin, Base):
    """Buchungsstelle. `position` 1 ist die führende Stelle, 2 die zweite Stelle."""

    __tablename__ = "booking_legs"
    __table_args__ = (
        UniqueConstraint("booking_id", "position"),
        CheckConstraint("position IN (1, 2)", name="position_valid"),
        CheckConstraint(in_values("side", Side), name="side_valid"),
        CheckConstraint(
            "(cost_center_id IS NULL) <> (account_id IS NULL)",
            name="exactly_one_stelle",
        ),
    )

    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String(6))
    cost_center_id: Mapped[str | None] = mapped_column(ForeignKey("cost_centers.id"), default=None)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), default=None)
