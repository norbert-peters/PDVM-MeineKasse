"""Anfangssalden (Vorträge) der Konten (siehe Architekturvorgabe 2.10)."""

from collections.abc import Sequence
from dataclasses import dataclass

from meine_kasse.application.ports import Today, UnitOfWorkFactory, local_today
from meine_kasse.application.services.booking_control_service import (
    MAX_YEAR,
    MIN_YEAR,
    load_or_create_control,
)
from meine_kasse.domain.entities import AccountOpeningBalance, AuditEntry
from meine_kasse.domain.errors import NotFoundError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.services.opening_rules import (
    OpeningEditability,
    OpeningSource,
    opening_editability,
    opening_for_year,
    opening_source,
)
from meine_kasse.domain.value_objects.money import format_euro


@dataclass(frozen=True, slots=True)
class OpeningBalanceRow:
    """Ein Konto im Überblick der Anfangssalden eines Jahres (Beträge in Cent)."""

    account_id: str
    label: str
    is_active: bool
    year: int
    opening_cents: int
    source: OpeningSource
    editability: OpeningEditability
    movement_cents: int
    balance_cents: int

    @property
    def editable(self) -> bool:
        return self.editability.editable


class OpeningBalanceService:
    def __init__(self, uow_factory: UnitOfWorkFactory, today: Today = local_today) -> None:
        self._uow_factory = uow_factory
        self._today = today

    def get_overview(self, year: int) -> Sequence[OpeningBalanceRow]:
        """Anfangssalden aller Konten zum 01.01. des Jahres."""
        _validate_year(year)
        with self._uow_factory() as uow:
            load_or_create_control(uow, self._today)
            movements = uow.bookings.account_year_movements()
            closed_months = uow.closures.closed_months()
            closed_years = uow.closures.closed_years()
            manual_by_account = {o.account_id: o for o in uow.opening_balances.list_all()}
            rows = []
            for account in uow.accounts.list_all():
                manual = manual_by_account.get(account.id)
                before = {y: c for (a, y), c in movements.items() if a == account.id and y < year}
                in_year = movements.get((account.id, year), 0)
                has_prior = bool(before)
                opening = opening_for_year(
                    year=year, manual=manual, movements_before_year_cents=sum(before.values())
                )
                rows.append(
                    OpeningBalanceRow(
                        account_id=account.id,
                        label=f"{account.number} {account.name}",
                        is_active=account.is_active,
                        year=year,
                        opening_cents=opening,
                        source=opening_source(
                            year=year, manual=manual, has_bookings_before_year=has_prior
                        ),
                        editability=opening_editability(
                            year=year,
                            manual=manual,
                            has_bookings_before_year=has_prior,
                            closed_months=closed_months,
                            closed_years=closed_years,
                        ),
                        movement_cents=in_year,
                        balance_cents=opening + in_year,
                    )
                )
            return rows

    def set_opening_balance(
        self, account_id: str, year: int, amount_cents: int, *, actor_id: str
    ) -> None:
        """Erfasst oder ändert den Vortrag eines Kontos zum 01.01. des Jahres."""
        _validate_year(year)
        with self._uow_factory() as uow:
            load_or_create_control(uow, self._today)
            label, manual = self._check_editable(uow, account_id, year)
            if manual is not None and (manual.year, manual.amount_cents) == (year, amount_cents):
                return
            uow.opening_balances.save(
                AccountOpeningBalance(
                    id=manual.id if manual else new_id(),
                    account_id=account_id,
                    year=year,
                    amount_cents=amount_cents,
                )
            )
            uow.audit.add(
                AuditEntry(
                    name="ACCOUNT_OPENING_SET",
                    entity="account_opening_balances",
                    entity_id=account_id,
                    user_id=actor_id,
                    old_value=_describe(manual),
                    new_value=f"{year}: {format_euro(amount_cents)} ({label})",
                )
            )
            uow.commit()

    def clear_opening_balance(self, account_id: str, year: int, *, actor_id: str) -> None:
        """Entfernt den manuell erfassten Vortrag (Kontostand startet dann bei 0,00 €)."""
        _validate_year(year)
        with self._uow_factory() as uow:
            load_or_create_control(uow, self._today)
            label, manual = self._check_editable(uow, account_id, year)
            if manual is None:
                return
            uow.opening_balances.delete(account_id)
            uow.audit.add(
                AuditEntry(
                    name="ACCOUNT_OPENING_CLEARED",
                    entity="account_opening_balances",
                    entity_id=account_id,
                    user_id=actor_id,
                    old_value=_describe(manual),
                )
            )
            uow.commit()

    @staticmethod
    def _check_editable(
        uow: UnitOfWork, account_id: str, year: int
    ) -> tuple[str, AccountOpeningBalance | None]:
        account = uow.accounts.get(account_id)
        if account is None:
            raise NotFoundError("Das Konto wurde nicht gefunden.")
        manual = uow.opening_balances.get(account_id)
        has_prior = any(
            a == account_id and y < year for (a, y) in uow.bookings.account_year_movements()
        )
        editability = opening_editability(
            year=year,
            manual=manual,
            has_bookings_before_year=has_prior,
            closed_months=uow.closures.closed_months(),
            closed_years=uow.closures.closed_years(),
        )
        if not editability.editable:
            raise ValidationError(
                f"Der Anfangssaldo von '{account.name}' für {year} kann nicht geändert werden: "
                f"{editability.message}."
            )
        return f"{account.number} {account.name}", manual


def _validate_year(year: int) -> None:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValidationError(f"Das Jahr muss zwischen {MIN_YEAR} und {MAX_YEAR} liegen.")


def _describe(opening: AccountOpeningBalance | None) -> str | None:
    if opening is None:
        return None
    return f"{opening.year}: {format_euro(opening.amount_cents)}"
