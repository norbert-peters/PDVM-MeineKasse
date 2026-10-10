from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import BookingControl
from meine_kasse.infrastructure.database.models import BookingControlModel


def _to_entity(model: BookingControlModel) -> BookingControl:
    return BookingControl(
        id=model.id,
        name=model.name,
        planning_enabled=model.planning_enabled,
        current_year=model.current_year,
        current_month=model.current_month,
        last_closed_year=model.last_closed_year,
        last_closed_month=model.last_closed_month,
    )


class SqlBookingControlRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active(self) -> BookingControl | None:
        statement = select(BookingControlModel).where(BookingControlModel.is_active.is_(True))
        model = self._session.scalars(statement).first()
        return None if model is None else _to_entity(model)

    def add(self, control: BookingControl) -> None:
        self._session.add(
            BookingControlModel(
                id=control.id,
                name=control.name,
                is_active=True,
                planning_enabled=control.planning_enabled,
                current_year=control.current_year,
                current_month=control.current_month,
                last_closed_year=control.last_closed_year,
                last_closed_month=control.last_closed_month,
            )
        )
        self._session.flush()

    def update(self, control: BookingControl) -> None:
        model = self._session.get(BookingControlModel, control.id)
        if model is None:
            raise LookupError(f"Buchungssteuerung {control.id} existiert nicht.")
        model.name = control.name
        model.planning_enabled = control.planning_enabled
        model.current_year = control.current_year
        model.current_month = control.current_month
        model.last_closed_year = control.last_closed_year
        model.last_closed_month = control.last_closed_month
        self._session.flush()
