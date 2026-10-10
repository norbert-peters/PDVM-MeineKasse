from datetime import date

import pytest

from meine_kasse.application.services.booking_control_service import BookingControlService
from meine_kasse.domain.errors import ValidationError
from meine_kasse.infrastructure.database.models import AuditLogModel
from meine_kasse.infrastructure.database.session import Database


def test_control_is_initialized_with_the_current_month_and_planning_off(
    booking_control: BookingControlService,
) -> None:
    control = booking_control.get()
    assert (control.current_year, control.current_month) == (2026, 5)
    assert control.planning_enabled is False
    assert booking_control.get().id == control.id


def test_update_changes_month_and_planning_and_is_audited(
    booking_control: BookingControlService, database: Database
) -> None:
    booking_control.update(planning_enabled=True, current_year=2026, current_month=6)

    control = booking_control.get()
    assert (control.current_month, control.planning_enabled) == (6, True)
    with database.session_factory() as session:
        entries = [e for e in session.query(AuditLogModel) if e.name == "BOOKING_CONTROL_UPDATED"]
    (entry,) = entries
    assert "05/2026" in (entry.old_value or "")
    assert "06/2026" in (entry.new_value or "")


def test_update_without_changes_writes_no_audit_entry(
    booking_control: BookingControlService, database: Database
) -> None:
    booking_control.update(planning_enabled=False, current_year=2026, current_month=5)
    with database.session_factory() as session:
        assert not [e for e in session.query(AuditLogModel) if e.name == "BOOKING_CONTROL_UPDATED"]


@pytest.mark.parametrize(("year", "month"), [(2026, 0), (2026, 13), (1800, 5), (2300, 5)])
def test_update_rejects_invalid_period(
    booking_control: BookingControlService, year: int, month: int
) -> None:
    with pytest.raises(ValidationError):
        booking_control.update(planning_enabled=False, current_year=year, current_month=month)


def test_current_month_must_be_after_last_closed_month(
    booking_control: BookingControlService, database: Database
) -> None:
    from meine_kasse.infrastructure.database.models import BookingControlModel

    booking_control.get()
    with database.session_factory() as session:
        model = session.query(BookingControlModel).one()
        model.last_closed_year, model.last_closed_month = 2026, 4
        session.commit()

    with pytest.raises(ValidationError, match="04/2026"):
        booking_control.update(planning_enabled=False, current_year=2026, current_month=4)
    booking_control.update(planning_enabled=False, current_year=2026, current_month=5)
    assert date(2026, 5, 1)
