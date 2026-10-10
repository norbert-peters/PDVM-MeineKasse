"""Buchungssteuerung: aktueller Buchungsmonat und Planung (siehe Architekturvorgabe 4.2)."""

from dataclasses import replace

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.domain.entities import AuditEntry, BookingControl
from meine_kasse.domain.errors import ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork

MIN_YEAR = 1990
MAX_YEAR = 2100


def load_or_create_control(uow: UnitOfWork, today: Today) -> BookingControl:
    """Liefert die aktive Buchungssteuerung. Beim ersten Zugriff wird sie mit dem heutigen
    Monat angelegt (Planung zunächst aus)."""
    control = uow.booking_control.get_active()
    if control is not None:
        return control
    now = today()
    control = BookingControl(
        id=new_id(),
        name="Buchungssteuerung",
        planning_enabled=False,
        current_year=now.year,
        current_month=now.month,
    )
    uow.booking_control.add(control)
    uow.commit()
    return control


class BookingControlService:
    def __init__(self, uow_factory: UnitOfWorkFactory, today: Today = local_today) -> None:
        self._uow_factory = uow_factory
        self._today = today

    def get(self) -> BookingControl:
        with self._uow_factory() as uow:
            return load_or_create_control(uow, self._today)

    def update(
        self,
        *,
        planning_enabled: bool,
        current_year: int,
        current_month: int,
        actor_id: str | None = None,
    ) -> None:
        if not MIN_YEAR <= current_year <= MAX_YEAR:
            raise ValidationError(
                f"Das Buchungsjahr muss zwischen {MIN_YEAR} und {MAX_YEAR} liegen."
            )
        if not 1 <= current_month <= 12:
            raise ValidationError("Der Buchungsmonat muss zwischen 1 und 12 liegen.")
        with self._uow_factory() as uow:
            current = load_or_create_control(uow, self._today)
            if (
                current.last_closed_year is not None
                and current.last_closed_month is not None
                and (current_year, current_month)
                <= (current.last_closed_year, current.last_closed_month)
            ):
                raise ValidationError(
                    "Der aktuelle Buchungsmonat muss nach dem letzten abgeschlossenen Monat "
                    f"({current.last_closed_month:02d}/{current.last_closed_year}) liegen."
                )
            updated = replace(
                current,
                planning_enabled=planning_enabled,
                current_year=current_year,
                current_month=current_month,
            )
            if updated == current:
                return
            uow.booking_control.update(updated)
            uow.audit.add(
                AuditEntry(
                    name="BOOKING_CONTROL_UPDATED",
                    entity="booking_control",
                    entity_id=current.id,
                    user_id=actor_id,
                    old_value=_summary(current),
                    new_value=_summary(updated),
                )
            )
            uow.commit()


def _summary(control: BookingControl) -> str:
    planning = "an" if control.planning_enabled else "aus"
    return f"{control.current_month:02d}/{control.current_year}, Planung {planning}"
