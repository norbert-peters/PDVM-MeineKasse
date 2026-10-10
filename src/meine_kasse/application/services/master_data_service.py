"""Anlage und Abfrage von Kostenstellen und Konten."""

from collections.abc import Sequence
from datetime import date

from meine_kasse.application.ports import UnitOfWorkFactory
from meine_kasse.domain.entities import Account, AuditEntry, CostCenter
from meine_kasse.domain.enums import AccountType, CostCenterKind
from meine_kasse.domain.errors import DuplicateError, ValidationError
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.value_objects.iban import normalize_iban


class MasterDataService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def create_cost_center(
        self,
        *,
        number: str,
        name: str,
        valid_from: date,
        kind: CostCenterKind = CostCenterKind.STANDARD,
        notes: str = "",
        actor_id: str | None = None,
    ) -> str:
        number, name = (
            _required(number, "Die Kostenstellennummer"),
            _required(name, "Der Kostenstellenname"),
        )
        cost_center = CostCenter(
            id=new_id(),
            name=name,
            number=number,
            valid_from=valid_from,
            kind=kind,
            notes=notes.strip(),
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
        number, name = _required(number, "Die Kontonummer"), _required(name, "Die Kontobezeichnung")
        account = Account(
            id=new_id(),
            name=name,
            number=number,
            account_type=account_type,
            bank_name=bank_name.strip(),
            owner_name=owner_name.strip(),
            iban=normalize_iban(iban) if iban.strip() else None,
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

    def list_cost_centers(self) -> Sequence[CostCenter]:
        with self._uow_factory() as uow:
            return uow.cost_centers.list_all()

    def list_accounts(self) -> Sequence[Account]:
        with self._uow_factory() as uow:
            return uow.accounts.list_all()


def _required(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValidationError(f"{label} darf nicht leer sein.")
    return value
