from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import PeriodClosure, YearClosure
from meine_kasse.infrastructure.database.models import PeriodClosureModel, YearClosureModel


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
