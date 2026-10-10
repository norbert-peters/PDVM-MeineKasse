from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import Account
from meine_kasse.domain.enums import AccountType
from meine_kasse.infrastructure.database.models import AccountModel


def _to_entity(model: AccountModel) -> Account:
    return Account(
        id=model.id,
        name=model.name,
        number=model.number,
        account_type=AccountType(model.account_type),
        bank_name=model.bank_name,
        owner_name=model.owner_name,
        iban=model.iban,
        is_active=model.is_active,
    )


class SqlAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, account: Account) -> None:
        self._session.add(
            AccountModel(
                id=account.id,
                name=account.name,
                number=account.number,
                account_type=account.account_type.value,
                bank_name=account.bank_name,
                owner_name=account.owner_name,
                iban=account.iban,
                is_active=account.is_active,
            )
        )
        self._session.flush()

    def get(self, account_id: str) -> Account | None:
        model = self._session.get(AccountModel, account_id)
        return None if model is None else _to_entity(model)

    def get_by_number(self, number: str) -> Account | None:
        statement = select(AccountModel).where(AccountModel.number == number)
        model = self._session.scalars(statement).first()
        return None if model is None else _to_entity(model)

    def list_all(self) -> Sequence[Account]:
        statement = select(AccountModel).order_by(AccountModel.number)
        return [_to_entity(model) for model in self._session.scalars(statement)]
