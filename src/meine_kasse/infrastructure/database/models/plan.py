from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from meine_kasse.domain.enums import PlanMode
from meine_kasse.infrastructure.database.base import Base
from meine_kasse.infrastructure.database.models.mixins import (
    IdNameMixin,
    TimestampMixin,
    in_values,
)


class CostCenterPlanModel(IdNameMixin, TimestampMixin, Base):
    """Jahresplan einer Kostenstelle. Der wirksame Ansatz ist Basisansatz + Ansatzumbuchungen."""

    __tablename__ = "cost_center_plans"
    __table_args__ = (
        UniqueConstraint("cost_center_id", "year"),
        CheckConstraint("base_budget_cents >= 0", name="base_budget_not_negative"),
    )

    cost_center_id: Mapped[str] = mapped_column(ForeignKey("cost_centers.id"))
    year: Mapped[int] = mapped_column(Integer)
    base_budget_cents: Mapped[int] = mapped_column(Integer, default=0)
    budget_transfer_cents: Mapped[int] = mapped_column(Integer, default=0)
    reserve_carry_in_cents: Mapped[int] = mapped_column(Integer, default=0)
    reserve_carry_out_cents: Mapped[int] = mapped_column(Integer, default=0)


class MonthlyPlanModel(IdNameMixin, TimestampMixin, Base):
    __tablename__ = "monthly_plans"
    __table_args__ = (
        UniqueConstraint("cost_center_plan_id", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_valid"),
        CheckConstraint("plan_cents >= 0", name="plan_not_negative"),
        CheckConstraint(in_values("plan_mode", PlanMode), name="plan_mode_valid"),
    )

    cost_center_plan_id: Mapped[str] = mapped_column(
        ForeignKey("cost_center_plans.id", ondelete="CASCADE")
    )
    month: Mapped[int] = mapped_column(Integer)
    plan_cents: Mapped[int] = mapped_column(Integer, default=0)
    reserve_plan_cents: Mapped[int] = mapped_column(Integer, default=0)
    plan_mode: Mapped[str] = mapped_column(String(20), default=PlanMode.MONTHLY.value)


class MonthlyActualModel(IdNameMixin, TimestampMixin, Base):
    """Projektion der Ist-Buchungen. Soll und Haben sind getrennt und vorzeichenbehaftet."""

    __tablename__ = "monthly_actuals"
    __table_args__ = (
        UniqueConstraint("cost_center_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_valid"),
    )

    cost_center_id: Mapped[str] = mapped_column(ForeignKey("cost_centers.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    debit_cents: Mapped[int] = mapped_column(Integer, default=0)
    credit_cents: Mapped[int] = mapped_column(Integer, default=0)
    reserve_actual_cents: Mapped[int] = mapped_column(Integer, default=0)
