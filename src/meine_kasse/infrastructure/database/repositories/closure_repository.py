from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import ClosureReopening, PeriodClosure, YearClosure
from meine_kasse.domain.enums import ClosureKind
from meine_kasse.infrastructure.database.models import (
    ClosureReopeningModel,
    PeriodClosureModel,
    YearClosureModel,
)


class SqlClosureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def closed_months(self) -> set[tuple[int, int]]:
        rows = self._session.execute(select(PeriodClosureModel.year, PeriodClosureModel.month))
        return {(year, month) for year, month in rows}

    def closed_years(self) -> set[int]:
        return set(self._session.scalars(select(YearClosureModel.year)))

    def list_months(self) -> Sequence[PeriodClosure]:
        statement = select(PeriodClosureModel).order_by(
            PeriodClosureModel.year, PeriodClosureModel.month
        )
        return [
            PeriodClosure(
                id=model.id,
                year=model.year,
                month=model.month,
                closed_on=model.closed_on,
                closed_by_user_id=model.closed_by_user_id,
                signature=model.signature,
            )
            for model in self._session.scalars(statement)
        ]

    def list_years(self) -> Sequence[YearClosure]:
        statement = select(YearClosureModel).order_by(YearClosureModel.year)
        return [
            YearClosure(
                id=model.id,
                year=model.year,
                closed_on=model.closed_on,
                closed_by_user_id=model.closed_by_user_id,
                signature=model.signature,
            )
            for model in self._session.scalars(statement)
        ]

    def add_month(self, closure: PeriodClosure) -> None:
        self._session.add(
            PeriodClosureModel(
                id=closure.id,
                name=f"{closure.month:02d}/{closure.year}",
                year=closure.year,
                month=closure.month,
                closed_on=closure.closed_on,
                closed_by_user_id=closure.closed_by_user_id,
                signature=closure.signature,
            )
        )
        self._session.flush()

    def add_year(self, closure: YearClosure) -> None:
        self._session.add(
            YearClosureModel(
                id=closure.id,
                name=str(closure.year),
                year=closure.year,
                closed_on=closure.closed_on,
                closed_by_user_id=closure.closed_by_user_id,
                signature=closure.signature,
            )
        )
        self._session.flush()

    def delete_month(self, year: int, month: int) -> None:
        self._session.execute(
            delete(PeriodClosureModel).where(
                PeriodClosureModel.year == year, PeriodClosureModel.month == month
            )
        )
        self._session.flush()

    def delete_year(self, year: int) -> None:
        self._session.execute(delete(YearClosureModel).where(YearClosureModel.year == year))
        self._session.flush()

    def add_reopening(self, reopening: ClosureReopening) -> None:
        label = (
            f"{reopening.month:02d}/{reopening.year}" if reopening.month else str(reopening.year)
        )
        self._session.add(
            ClosureReopeningModel(
                id=reopening.id,
                name=f"{reopening.kind.value} {label}",
                kind=reopening.kind.value,
                year=reopening.year,
                month=reopening.month,
                reopened_on=reopening.reopened_on,
                reopened_by_user_id=reopening.reopened_by_user_id,
                reason=reopening.reason,
                previous_signature=reopening.previous_signature,
                previous_closed_on=reopening.previous_closed_on,
                previous_closed_by_user_id=reopening.previous_closed_by_user_id,
                signature_was_valid=reopening.signature_was_valid,
            )
        )
        self._session.flush()

    def list_reopenings(self) -> Sequence[ClosureReopening]:
        statement = select(ClosureReopeningModel).order_by(
            ClosureReopeningModel.created_at, ClosureReopeningModel.id
        )
        return [
            ClosureReopening(
                id=model.id,
                kind=ClosureKind(model.kind),
                year=model.year,
                month=model.month,
                reopened_on=model.reopened_on,
                reopened_by_user_id=model.reopened_by_user_id,
                reason=model.reason,
                previous_signature=model.previous_signature,
                previous_closed_on=model.previous_closed_on,
                previous_closed_by_user_id=model.previous_closed_by_user_id,
                signature_was_valid=model.signature_was_valid,
            )
            for model in self._session.scalars(statement)
        ]
