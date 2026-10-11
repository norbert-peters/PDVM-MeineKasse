from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import IdNameMixin, TimestampMixin


class AccountOpeningBalanceModel(IdNameMixin, TimestampMixin, Base):
    """Manuell erfasster Vortrag eines Kontos. Höchstens einer je Konto."""

    __tablename__ = "account_opening_balances"
    __table_args__ = (
        UniqueConstraint("account_id"),
        CheckConstraint("year BETWEEN 1990 AND 2100", name="year_valid"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    year: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)
