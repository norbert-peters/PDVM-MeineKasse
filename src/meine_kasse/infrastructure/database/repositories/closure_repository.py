from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.infrastructure.database.models import PeriodClosureModel, YearClosureModel


class SqlClosureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def closed_months(self) -> set[tuple[int, int]]:
        rows = self._session.execute(select(PeriodClosureModel.year, PeriodClosureModel.month))
        return {(year, month) for year, month in rows}

    def closed_years(self) -> set[int]:
        return set(self._session.scalars(select(YearClosureModel.year)))
