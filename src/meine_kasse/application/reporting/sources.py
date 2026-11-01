"""Quellzeilen der Datenquellen einer Auswertung (Architekturvorgabe 2.14).

Jede Funktion liefert Zeilen als Spaltenschlüssel → Rohwert (Cent, Datum, Text). Die Schlüssel
entsprechen dem Spaltenkatalog; formatiert wird erst in der Auswertungsmaschine.
"""

from collections.abc import Sequence
from typing import Any

from meine_kasse.application.services.planning_service import PlanView
from meine_kasse.domain.entities import Account, CostCenter
from meine_kasse.domain.enums import AccountType, BookingType, CostCenterKind, Side
from meine_kasse.domain.repositories import UnitOfWork

Row = dict[str, Any]
PlanTarget = tuple[CostCenter, int]

BOOKING_TYPE_NAMES = {
    BookingType.COST_CENTER_TO_ACCOUNT: "Kostenstelle → Konto",
    BookingType.ACCOUNT_TO_ACCOUNT: "Konto → Konto (alt)",
    BookingType.BUDGET_TRANSFER: "Ansatzumbuchung",
}
TRANSFER_NAME = "Umbuchung (Kostenstelle → Konto)"
ACCOUNT_TYPE_NAMES = {
    AccountType.CHECKING: "Giro",
    AccountType.SAVINGS: "Spar",
    AccountType.INVESTMENT: "Anlage",
    AccountType.RESERVE: "Rückstellung",
}
OPEN, CLOSED = "offen", "abgeschlossen"


def _label(item: CostCenter | Account) -> str:
    return f"{item.number} {item.name}"


def booking_rows(uow: UnitOfWork) -> list[Row]:
    bookings = uow.bookings.list_filtered(None, None)
    cost_centers = {item.id: _label(item) for item in uow.cost_centers.list_all()}
    accounts = {item.id: _label(item) for item in uow.accounts.list_all()}
    users = {item.id: item.display_name for item in uow.users.list_all()}
    closed_months = uow.closures.closed_months()
    closed_years = uow.closures.closed_years()
    reversed_ids = {item.reversal_of_id for item in bookings if item.reversal_of_id}
    transfer_accounts: dict[str, list[tuple[str, str]]] = {}
    for booking in bookings:
        if booking.transfer_id:
            account_id = next((leg.account_id for leg in booking.legs if leg.account_id), "")
            transfer_accounts.setdefault(booking.transfer_id, []).append(
                (booking.id, accounts.get(account_id or "", ""))
            )

    rows = []
    for booking in bookings:
        closed = (
            booking.fiscal_year in closed_years
            or (booking.fiscal_year, booking.fiscal_month) in closed_months
        )
        status = [CLOSED if closed else OPEN]
        if booking.reversal_of_id:
            status.append("Storno")
        if booking.id in reversed_ids:
            status.append("storniert")
        booking_cost_centers = [
            cost_centers.get(leg.cost_center_id, "") for leg in booking.legs if leg.cost_center_id
        ]
        booking_accounts = [
            accounts.get(leg.account_id, "") for leg in booking.legs if leg.account_id
        ]
        counter_account = booking_accounts[1] if len(booking_accounts) > 1 else ""
        if booking.transfer_id:
            counter_account = next(
                (
                    name
                    for booking_id, name in transfer_accounts[booking.transfer_id]
                    if booking_id != booking.id
                ),
                "",
            )
        is_debit = booking.entry_side is Side.DEBIT
        rows.append(
            {
                "booking_date": booking.booking_date,
                "origin_date": booking.origin_date,
                "fiscal_year": booking.fiscal_year,
                "fiscal_month": booking.fiscal_month,
                "cost_center": booking_cost_centers[0] if booking_cost_centers else "",
                "account": booking_accounts[0] if booking_accounts else "",
                "counter_account": counter_account,
                "counter_cost_center": (
                    booking_cost_centers[1] if len(booking_cost_centers) > 1 else ""
                ),
                "booking_type": (
                    TRANSFER_NAME
                    if booking.transfer_id
                    else BOOKING_TYPE_NAMES[booking.booking_type]
                ),
                "debit": booking.amount_cents if is_debit else None,
                "credit": None if is_debit else booking.amount_cents,
                "booking_text": booking.booking_text,
                "merchant": booking.merchant,
                "status": ", ".join(status),
                "user": users.get(booking.created_by_user_id, ""),
            }
        )
    return rows


def plan_targets(uow: UnitOfWork) -> list[PlanTarget]:
    """Kostenstellen mit Plan und ihre Planjahre. Die Planansichten folgen außerhalb der UoW."""
    targets: list[PlanTarget] = []
    for cost_center in uow.cost_centers.list_all():
        if cost_center.kind is CostCenterKind.STANDARD:
            targets.extend(
                (cost_center, plan.year) for plan in uow.plans.plans_of_cost_center(cost_center.id)
            )
    return targets


def plan_actual_rows(views: Sequence[tuple[CostCenter, PlanView]]) -> list[Row]:
    rows: list[Row] = []
    for cost_center, view in views:
        cumulative = 0
        for month in view.months:
            cumulative += month.movement_cents
            values = (
                month.plan_cents,
                month.debit_cents,
                month.credit_cents,
                month.reserve_plan_cents,
                month.reserve_release_cents,
            )
            if not any(values):
                continue
            rows.append(
                {
                    "cost_center": _label(cost_center),
                    "year": view.year,
                    "month": month.month,
                    "status": CLOSED if month.is_closed else OPEN,
                    "debit": month.debit_cents,
                    "credit": month.credit_cents,
                    "movement": month.movement_cents,
                    "plan": month.plan_cents,
                    "deviation": month.deviation_cents,
                    "budget": view.effective_budget_cents,
                    "remaining_budget": view.effective_budget_cents - cumulative,
                    "reserve_contribution": month.reserve_plan_cents,
                    "reserve_release": month.reserve_release_cents,
                    "reserve_balance": month.reserve_balance_cents,
                }
            )
    return rows


def account_rows(uow: UnitOfWork) -> list[Row]:
    debit: dict[str, int] = {}
    credit: dict[str, int] = {}
    for booking in uow.bookings.list_filtered(None, None):
        for leg in booking.legs:
            if leg.account_id is None:
                continue
            target = debit if leg.side is Side.DEBIT else credit
            target[leg.account_id] = target.get(leg.account_id, 0) + booking.amount_cents
    rows = []
    for account in uow.accounts.list_all():
        opening = uow.opening_balances.get(account.id)
        opening_cents = opening.amount_cents if opening else 0
        soll, haben = debit.get(account.id, 0), credit.get(account.id, 0)
        rows.append(
            {
                "account": _label(account),
                "account_type": ACCOUNT_TYPE_NAMES[account.account_type],
                "status": "Aktiv" if account.is_active else "Inaktiv",
                "opening_balance": opening_cents,
                "debit": soll,
                "credit": haben,
                "balance": opening_cents + haben - soll,
            }
        )
    return rows
