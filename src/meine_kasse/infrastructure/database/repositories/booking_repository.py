from collections import defaultdict
from collections.abc import Mapping, Sequence

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import Booking, BookingLeg
from meine_kasse.domain.enums import BookingType, Side
from meine_kasse.infrastructure.database.models import BookingLegModel, BookingModel


def _leg_to_entity(model: BookingLegModel) -> BookingLeg:
    return BookingLeg(
        position=model.position,
        side=Side(model.side),
        cost_center_id=model.cost_center_id,
        account_id=model.account_id,
    )


def _to_entity(model: BookingModel, legs: Sequence[BookingLegModel]) -> Booking:
    ordered = sorted(legs, key=lambda leg: leg.position)
    first, second = (_leg_to_entity(leg) for leg in ordered)
    return Booking(
        id=model.id,
        name=model.name,
        origin_date=model.origin_date,
        booking_date=model.booking_date,
        booking_type=BookingType(model.booking_type),
        entry_side=Side(model.entry_side),
        amount_cents=model.amount_cents,
        merchant=model.merchant,
        booking_text=model.booking_text,
        reversal_of_id=model.reversal_of_id,
        fiscal_year=model.fiscal_year,
        fiscal_month=model.fiscal_month,
        created_by_user_id=model.created_by_user_id,
        legs=(first, second),
    )


def _leg_models(booking: Booking) -> list[BookingLegModel]:
    return [
        BookingLegModel(
            booking_id=booking.id,
            position=leg.position,
            side=leg.side.value,
            cost_center_id=leg.cost_center_id,
            account_id=leg.account_id,
        )
        for leg in booking.legs
    ]


class SqlBookingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, booking: Booking) -> None:
        self._session.add(
            BookingModel(
                id=booking.id,
                name=booking.name,
                origin_date=booking.origin_date,
                booking_date=booking.booking_date,
                booking_type=booking.booking_type.value,
                entry_side=booking.entry_side.value,
                amount_cents=booking.amount_cents,
                merchant=booking.merchant,
                booking_text=booking.booking_text,
                reversal_of_id=booking.reversal_of_id,
                fiscal_year=booking.fiscal_year,
                fiscal_month=booking.fiscal_month,
                created_by_user_id=booking.created_by_user_id,
            )
        )
        self._session.flush()
        self._session.add_all(_leg_models(booking))
        self._session.flush()

    def update(self, booking: Booking) -> None:
        model = self._session.get(BookingModel, booking.id)
        if model is None:
            raise LookupError(f"Buchung {booking.id} existiert nicht.")
        model.name = booking.name
        model.origin_date = booking.origin_date
        model.booking_date = booking.booking_date
        model.booking_type = booking.booking_type.value
        model.entry_side = booking.entry_side.value
        model.amount_cents = booking.amount_cents
        model.merchant = booking.merchant
        model.booking_text = booking.booking_text
        model.fiscal_year = booking.fiscal_year
        model.fiscal_month = booking.fiscal_month
        self._session.execute(
            delete(BookingLegModel).where(BookingLegModel.booking_id == booking.id)
        )
        self._session.flush()
        self._session.add_all(_leg_models(booking))
        self._session.flush()

    def delete(self, booking_id: str) -> None:
        self._session.execute(
            delete(BookingLegModel).where(BookingLegModel.booking_id == booking_id)
        )
        model = self._session.get(BookingModel, booking_id)
        if model is not None:
            self._session.delete(model)
        self._session.flush()

    def get(self, booking_id: str) -> Booking | None:
        model = self._session.get(BookingModel, booking_id)
        if model is None:
            return None
        legs = self._session.scalars(
            select(BookingLegModel).where(BookingLegModel.booking_id == booking_id)
        ).all()
        return _to_entity(model, legs)

    def has_reversal(self, booking_id: str) -> bool:
        statement = select(func.count()).where(BookingModel.reversal_of_id == booking_id)
        return (self._session.scalar(statement) or 0) > 0

    def list_filtered(self, year: int | None, month: int | None) -> Sequence[Booking]:
        statement = select(BookingModel)
        if year is not None:
            statement = statement.where(BookingModel.fiscal_year == year)
        if month is not None:
            statement = statement.where(BookingModel.fiscal_month == month)
        statement = statement.order_by(
            BookingModel.booking_date, BookingModel.created_at, BookingModel.id
        )
        models = self._session.scalars(statement).all()
        if not models:
            return []
        legs_by_booking: dict[str, list[BookingLegModel]] = defaultdict(list)
        leg_statement = select(BookingLegModel).where(
            BookingLegModel.booking_id.in_([model.id for model in models])
        )
        for leg in self._session.scalars(leg_statement):
            legs_by_booking[leg.booking_id].append(leg)
        return [_to_entity(model, legs_by_booking[model.id]) for model in models]

    def account_balance_cents(self, account_id: str) -> int:
        signed = case(
            (BookingLegModel.side == Side.CREDIT.value, BookingModel.amount_cents),
            else_=-BookingModel.amount_cents,
        )
        statement = (
            select(func.coalesce(func.sum(signed), 0))
            .select_from(BookingLegModel)
            .join(BookingModel, BookingModel.id == BookingLegModel.booking_id)
            .where(BookingLegModel.account_id == account_id)
        )
        return int(self._session.scalar(statement) or 0)

    def cost_center_actual_totals(self) -> Mapping[tuple[str, int, int], tuple[int, int]]:
        statement = (
            select(
                BookingLegModel.cost_center_id,
                BookingModel.fiscal_year,
                BookingModel.fiscal_month,
                BookingLegModel.side,
                func.sum(BookingModel.amount_cents),
            )
            .join(BookingModel, BookingModel.id == BookingLegModel.booking_id)
            .where(
                BookingLegModel.cost_center_id.is_not(None),
                BookingModel.booking_type != BookingType.BUDGET_TRANSFER.value,
            )
            .group_by(
                BookingLegModel.cost_center_id,
                BookingModel.fiscal_year,
                BookingModel.fiscal_month,
                BookingLegModel.side,
            )
        )
        totals: dict[tuple[str, int, int], list[int]] = defaultdict(lambda: [0, 0])
        for cost_center_id, year, month, side, amount in self._session.execute(statement):
            if cost_center_id is None:
                continue
            index = 0 if side == Side.DEBIT.value else 1
            totals[(cost_center_id, year, month)][index] += int(amount)
        return {key: (value[0], value[1]) for key, value in totals.items()}

    def budget_transfer_totals(self) -> Mapping[tuple[str, int], int]:
        signed = case(
            (BookingLegModel.side == Side.CREDIT.value, BookingModel.amount_cents),
            else_=-BookingModel.amount_cents,
        )
        statement = (
            select(BookingLegModel.cost_center_id, BookingModel.fiscal_year, func.sum(signed))
            .join(BookingModel, BookingModel.id == BookingLegModel.booking_id)
            .where(
                BookingLegModel.cost_center_id.is_not(None),
                BookingModel.booking_type == BookingType.BUDGET_TRANSFER.value,
            )
            .group_by(BookingLegModel.cost_center_id, BookingModel.fiscal_year)
        )
        return {
            (cost_center_id, year): int(total)
            for cost_center_id, year, total in self._session.execute(statement)
        }
