import json
from datetime import date

import pytest
from sqlalchemy import select

from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import AccountType, CostCenterKind
from meine_kasse.domain.errors import DuplicateError, NotFoundError, ValidationError
from meine_kasse.infrastructure.database.models import AuditLogModel
from meine_kasse.infrastructure.database.session import Database

IBAN_PLAIN = "DE89370400440532013000"
IBAN_OTHER = "DE02120300000000202051"


def _audit(database: Database, name: str) -> list[AuditLogModel]:
    with database.session_factory() as session:
        return list(session.scalars(select(AuditLogModel).where(AuditLogModel.name == name)))


@pytest.fixture
def cost_center_id(master_data: MasterDataService) -> str:
    return master_data.create_cost_center(
        number="100", name="Lebensmittel", valid_from=date(2026, 1, 1), notes="alt"
    )


@pytest.fixture
def account_id(master_data: MasterDataService) -> str:
    return master_data.create_account(
        number="1000",
        name="Girokonto",
        account_type=AccountType.CHECKING,
        owner_name="Anna Muster",
        iban=IBAN_PLAIN,
    )


def test_update_cost_center_changes_fields_and_audits_the_difference(
    master_data: MasterDataService, database: Database, cost_center_id: str
) -> None:
    master_data.update_cost_center(
        cost_center_id,
        number="110",
        name="Lebensmittel & Drogerie",
        valid_from=date(2026, 2, 1),
        notes="neu",
    )

    updated = master_data.get_cost_center(cost_center_id)
    assert (updated.number, updated.name, updated.valid_from, updated.notes) == (
        "110",
        "Lebensmittel & Drogerie",
        date(2026, 2, 1),
        "neu",
    )
    assert updated.kind is CostCenterKind.STANDARD
    (entry,) = _audit(database, "COST_CENTER_UPDATED")
    assert json.loads(entry.old_value or "")["number"] == "100"
    assert json.loads(entry.new_value or "")["number"] == "110"


def test_update_without_changes_writes_no_audit_entry(
    master_data: MasterDataService, database: Database, cost_center_id: str
) -> None:
    master_data.update_cost_center(
        cost_center_id, number="100", name="Lebensmittel", valid_from=date(2026, 1, 1), notes="alt"
    )
    assert _audit(database, "COST_CENTER_UPDATED") == []


def test_cost_center_number_must_stay_unique_on_update(
    master_data: MasterDataService, cost_center_id: str
) -> None:
    master_data.create_cost_center(number="200", name="Reisen", valid_from=date(2026, 1, 1))
    with pytest.raises(DuplicateError):
        master_data.update_cost_center(
            cost_center_id, number="200", name="Lebensmittel", valid_from=date(2026, 1, 1)
        )
    master_data.update_cost_center(
        cost_center_id, number="100", name="Neu benannt", valid_from=date(2026, 1, 1)
    )


def test_update_unknown_cost_center_is_reported(master_data: MasterDataService) -> None:
    with pytest.raises(NotFoundError):
        master_data.update_cost_center(
            "unbekannt", number="1", name="A", valid_from=date(2026, 1, 1)
        )


def test_deactivate_and_reactivate_cost_center(
    master_data: MasterDataService, database: Database, cost_center_id: str
) -> None:
    master_data.set_cost_center_active(cost_center_id, False, actor_id=None)

    assert master_data.list_cost_centers(include_inactive=False) == []
    assert [c.number for c in master_data.list_cost_centers()] == ["100"]
    assert len(_audit(database, "COST_CENTER_DEACTIVATED")) == 1

    master_data.set_cost_center_active(cost_center_id, True, actor_id=None)
    assert len(master_data.list_cost_centers(include_inactive=False)) == 1
    assert len(_audit(database, "COST_CENTER_ACTIVATED")) == 1


def test_setting_the_same_active_state_is_a_noop(
    master_data: MasterDataService, database: Database, cost_center_id: str
) -> None:
    master_data.set_cost_center_active(cost_center_id, True, actor_id=None)
    assert _audit(database, "COST_CENTER_ACTIVATED") == []


def test_update_account_keeps_iban_out_of_the_audit_log(
    master_data: MasterDataService, database: Database, account_id: str
) -> None:
    master_data.update_account(
        account_id,
        number="1000",
        name="Girokonto Haushalt",
        account_type=AccountType.SAVINGS,
        owner_name="Anna Muster",
        iban=IBAN_OTHER,
    )

    updated = master_data.get_account(account_id)
    assert updated.name == "Girokonto Haushalt"
    assert updated.account_type is AccountType.SAVINGS
    assert updated.iban == IBAN_OTHER
    (entry,) = _audit(database, "ACCOUNT_UPDATED")
    combined = f"{entry.old_value} {entry.new_value}"
    assert IBAN_PLAIN not in combined
    assert IBAN_OTHER not in combined
    assert "iban" in combined


def test_update_account_can_clear_the_iban_but_not_set_an_invalid_one(
    master_data: MasterDataService, account_id: str
) -> None:
    with pytest.raises(ValidationError):
        master_data.update_account(
            account_id,
            number="1000",
            name="Girokonto",
            account_type=AccountType.CHECKING,
            iban="DE00",
        )
    master_data.update_account(
        account_id, number="1000", name="Girokonto", account_type=AccountType.CHECKING, iban=""
    )
    assert master_data.get_account(account_id).iban is None


def test_account_number_must_stay_unique_on_update(
    master_data: MasterDataService, account_id: str
) -> None:
    master_data.create_account(number="2000", name="Spar", account_type=AccountType.SAVINGS)
    with pytest.raises(DuplicateError):
        master_data.update_account(
            account_id, number="2000", name="Girokonto", account_type=AccountType.CHECKING
        )


def test_deactivate_account(master_data: MasterDataService, account_id: str) -> None:
    master_data.set_account_active(account_id, False)
    assert master_data.list_accounts(include_inactive=False) == []
    assert len(master_data.list_accounts()) == 1
