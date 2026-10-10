from dataclasses import dataclass

from meine_kasse.domain.enums import AccountType


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    name: str
    number: str
    account_type: AccountType
    bank_name: str
    owner_name: str
    iban: str | None
    is_active: bool = True
