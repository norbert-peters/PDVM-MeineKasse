from datetime import date

import pytest

from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import AccountType, CostCenterKind
from meine_kasse.domain.errors import DuplicateError, ValidationError


def test_create_and_list_cost_centers(master_data: MasterDataService) -> None:
    master_data.create_cost_center(
        number="200", name="Reisen", valid_from=date(2026, 1, 1), kind=CostCenterKind.WITHOUT_PLAN
    )
    master_data.create_cost_center(number="100", name="Lebensmittel", valid_from=date(2026, 1, 1))

    listed = master_data.list_cost_centers()
    assert [item.number for item in listed] == ["100", "200"]
    assert listed[1].kind is CostCenterKind.WITHOUT_PLAN


def test_cost_center_number_must_be_unique(master_data: MasterDataService) -> None:
    master_data.create_cost_center(number="100", name="A", valid_from=date(2026, 1, 1))
    with pytest.raises(DuplicateError):
        master_data.create_cost_center(number="100", name="B", valid_from=date(2026, 1, 1))


def test_cost_center_requires_number_and_name(master_data: MasterDataService) -> None:
    with pytest.raises(ValidationError):
        master_data.create_cost_center(number=" ", name="A", valid_from=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        master_data.create_cost_center(number="1", name="", valid_from=date(2026, 1, 1))


def test_account_with_valid_iban_is_normalized(master_data: MasterDataService) -> None:
    master_data.create_account(
        number="1000",
        name="Girokonto",
        account_type=AccountType.CHECKING,
        owner_name="Anna Muster",
        iban="de89 3704 0044 0532 0130 00",
    )
    (account,) = master_data.list_accounts()
    assert account.iban == "DE89370400440532013000"
    assert account.account_type is AccountType.CHECKING


def test_account_iban_is_optional_but_validated(master_data: MasterDataService) -> None:
    master_data.create_account(number="2000", name="Bar", account_type=AccountType.SAVINGS)
    with pytest.raises(ValidationError):
        master_data.create_account(
            number="3000", name="X", account_type=AccountType.CHECKING, iban="DE00"
        )


def test_account_number_must_be_unique(master_data: MasterDataService) -> None:
    master_data.create_account(number="1000", name="A", account_type=AccountType.CHECKING)
    with pytest.raises(DuplicateError):
        master_data.create_account(number="1000", name="B", account_type=AccountType.SAVINGS)
