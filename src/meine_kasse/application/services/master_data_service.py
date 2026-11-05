"""Pflege von Kostenstellen und Konten.

Stammdaten werden nie gelöscht, sondern deaktiviert. Änderungen werden protokolliert.
Die Kostenstellenart und bei Einnahmen der Modus sind nach dem Anlegen fest, weil sie Planung
und Ansatzsperre bestimmen.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from meine_kasse.application.audit import describe_changes
from meine_kasse.application.ports import UnitOfWorkFactory
from meine_kasse.domain.entities import Account, AuditEntry, CostCenter
from meine_kasse.domain.enums import AccountType, CostCenterKind, IncomeMode
from meine_kasse.domain.errors import DuplicateError, NotFoundError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.domain.value_objects.iban import normalize_iban

_COST_CENTER_FIELDS = ("number", "name", "valid_from", "notes", "always_in_plan_report")
_ACCOUNT_FIELDS = ("number", "name", "account_type", "bank_name", "owner_name", "iban")
_ACCOUNT_PROTECTED = ("iban",)


class MasterDataService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    # Kostenstellen

    def create_cost_center(
        self,
        *,
        number: str,
        name: str,
        valid_from: date,
        kind: CostCenterKind = CostCenterKind.STANDARD,
        income_mode: IncomeMode | None = None,
        always_in_plan_report: bool = False,
        notes: str = "",
        actor_id: str | None = None,
    ) -> str:
        number = _required(number, "Die Kostenstellennummer")
        name = _required(name, "Der Kostenstellenname")
        if kind is CostCenterKind.INCOME:
            income_mode = income_mode or IncomeMode.PLAN
        elif income_mode is not None:
            raise ValidationError("Einen Einnahmemodus gibt es nur bei Einnahmen-Kostenstellen.")
        _check_plan_report(kind, always_in_plan_report)
        cost_center = CostCenter(
            id=new_id(),
            name=name,
            number=number,
            valid_from=valid_from,
            kind=kind,
            notes=notes.strip(),
            income_mode=income_mode,
            always_in_plan_report=always_in_plan_report,
        )
        with self._uow_factory() as uow:
            if uow.cost_centers.get_by_number(number) is not None:
                raise DuplicateError(f"Die Kostenstellennummer '{number}' ist bereits vergeben.")
            uow.cost_centers.add(cost_center)
            uow.audit.add(
                AuditEntry(
                    name="COST_CENTER_CREATED",
                    entity="cost_centers",
                    entity_id=cost_center.id,
                    user_id=actor_id,
                    new_value=f"{number} {name}",
                )
            )
            uow.commit()
        return cost_center.id

    def get_cost_center(self, cost_center_id: str) -> CostCenter:
        with self._uow_factory() as uow:
            return _get_cost_center(uow, cost_center_id)

    def update_cost_center(
        self,
        cost_center_id: str,
        *,
        number: str,
        name: str,
        valid_from: date,
        notes: str = "",
        always_in_plan_report: bool | None = None,
        actor_id: str | None = None,
    ) -> None:
        number = _required(number, "Die Kostenstellennummer")
        name = _required(name, "Der Kostenstellenname")
        with self._uow_factory() as uow:
            current = _get_cost_center(uow, cost_center_id)
            flag = (
                current.always_in_plan_report
                if always_in_plan_report is None
                else always_in_plan_report
            )
            _check_plan_report(current.kind, flag)
            updated = replace(
                current,
                number=number,
                name=name,
                valid_from=valid_from,
                notes=notes.strip(),
                always_in_plan_report=flag,
            )
            changes = describe_changes(current, updated, _COST_CENTER_FIELDS)
            if changes is None:
                return
            other = uow.cost_centers.get_by_number(number)
            if other is not None and other.id != cost_center_id:
                raise DuplicateError(f"Die Kostenstellennummer '{number}' ist bereits vergeben.")
            uow.cost_centers.update(updated)
            uow.audit.add(
                AuditEntry(
                    name="COST_CENTER_UPDATED",
                    entity="cost_centers",
                    entity_id=cost_center_id,
                    user_id=actor_id,
                    old_value=changes[0],
                    new_value=changes[1],
                )
            )
            uow.commit()

    def set_cost_center_active(
        self, cost_center_id: str, active: bool, *, actor_id: str | None = None
    ) -> None:
        with self._uow_factory() as uow:
            current = _get_cost_center(uow, cost_center_id)
            if current.is_active == active:
                return
            uow.cost_centers.update(replace(current, is_active=active))
            uow.audit.add(
                AuditEntry(
                    name="COST_CENTER_ACTIVATED" if active else "COST_CENTER_DEACTIVATED",
                    entity="cost_centers",
                    entity_id=cost_center_id,
                    user_id=actor_id,
                    new_value=f"{current.number} {current.name}",
                )
            )
            uow.commit()

    def list_cost_centers(self, *, include_inactive: bool = True) -> Sequence[CostCenter]:
        with self._uow_factory() as uow:
            items = uow.cost_centers.list_all()
        return [item for item in items if include_inactive or item.is_active]

    # Konten

    def create_account(
        self,
        *,
        number: str,
        name: str,
        account_type: AccountType,
        bank_name: str = "",
        owner_name: str = "",
        iban: str = "",
        actor_id: str | None = None,
    ) -> str:
        number = _required(number, "Die Kontonummer")
        name = _required(name, "Die Kontobezeichnung")
        account = Account(
            id=new_id(),
            name=name,
            number=number,
            account_type=account_type,
            bank_name=bank_name.strip(),
            owner_name=owner_name.strip(),
            iban=_optional_iban(iban),
        )
        with self._uow_factory() as uow:
            if uow.accounts.get_by_number(number) is not None:
                raise DuplicateError(f"Die Kontonummer '{number}' ist bereits vergeben.")
            uow.accounts.add(account)
            uow.audit.add(
                AuditEntry(
                    name="ACCOUNT_CREATED",
                    entity="accounts",
                    entity_id=account.id,
                    user_id=actor_id,
                    new_value=f"{number} {name}",
                )
            )
            uow.commit()
        return account.id

    def get_account(self, account_id: str) -> Account:
        with self._uow_factory() as uow:
            return _get_account(uow, account_id)

    def update_account(
        self,
        account_id: str,
        *,
        number: str,
        name: str,
        account_type: AccountType,
        bank_name: str = "",
        owner_name: str = "",
        iban: str = "",
        actor_id: str | None = None,
    ) -> None:
        number = _required(number, "Die Kontonummer")
        name = _required(name, "Die Kontobezeichnung")
        new_iban = _optional_iban(iban)
        with self._uow_factory() as uow:
            current = _get_account(uow, account_id)
            updated = replace(
                current,
                number=number,
                name=name,
                account_type=account_type,
                bank_name=bank_name.strip(),
                owner_name=owner_name.strip(),
                iban=new_iban,
            )
            changes = describe_changes(
                current, updated, _ACCOUNT_FIELDS, protected=_ACCOUNT_PROTECTED
            )
            if changes is None:
                return
            other = uow.accounts.get_by_number(number)
            if other is not None and other.id != account_id:
                raise DuplicateError(f"Die Kontonummer '{number}' ist bereits vergeben.")
            uow.accounts.update(updated)
            uow.audit.add(
                AuditEntry(
                    name="ACCOUNT_UPDATED",
                    entity="accounts",
                    entity_id=account_id,
                    user_id=actor_id,
                    old_value=changes[0],
                    new_value=changes[1],
                )
            )
            uow.commit()

    def set_account_active(
        self, account_id: str, active: bool, *, actor_id: str | None = None
    ) -> None:
        with self._uow_factory() as uow:
            current = _get_account(uow, account_id)
            if current.is_active == active:
                return
            uow.accounts.update(replace(current, is_active=active))
            uow.audit.add(
                AuditEntry(
                    name="ACCOUNT_ACTIVATED" if active else "ACCOUNT_DEACTIVATED",
                    entity="accounts",
                    entity_id=account_id,
                    user_id=actor_id,
                    new_value=f"{current.number} {current.name}",
                )
            )
            uow.commit()

    def list_accounts(self, *, include_inactive: bool = True) -> Sequence[Account]:
        with self._uow_factory() as uow:
            items = uow.accounts.list_all()
        return [item for item in items if include_inactive or item.is_active]


def _check_plan_report(kind: CostCenterKind, always_in_plan_report: bool) -> None:
    if always_in_plan_report and kind is CostCenterKind.INCOME:
        raise ValidationError(
            "Einnahmen-Kostenstellen erscheinen in der Einnahmenauswertung, nicht in Plan/Ist."
        )


def _required(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValidationError(f"{label} darf nicht leer sein.")
    return value


def _optional_iban(value: str) -> str | None:
    return normalize_iban(value) if value.strip() else None


def _get_cost_center(uow: UnitOfWork, cost_center_id: str) -> CostCenter:
    cost_center = uow.cost_centers.get(cost_center_id)
    if cost_center is None:
        raise NotFoundError("Die Kostenstelle wurde nicht gefunden.")
    return cost_center


def _get_account(uow: UnitOfWork, account_id: str) -> Account:
    account = uow.accounts.get(account_id)
    if account is None:
        raise NotFoundError("Das Konto wurde nicht gefunden.")
    return account
