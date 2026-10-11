from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import AccountOpeningBalance
from meine_kasse.infrastructure.database.models import AccountOpeningBalanceModel


def _to_entity(model: AccountOpeningBalanceModel) -> AccountOpeningBalance:
    return AccountOpeningBalance(
        id=model.id,
        account_id=model.account_id,
        year=model.year,
        amount_cents=model.amount_cents,
    )


class SqlOpeningBalanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, account_id: str) -> AccountOpeningBalance | None:
        statement = select(AccountOpeningBalanceModel).where(
            AccountOpeningBalanceModel.account_id == account_id
        )
        model = self._session.scalars(statement).first()
        return None if model is None else _to_entity(model)

    def list_all(self) -> Sequence[AccountOpeningBalance]:
        statement = select(AccountOpeningBalanceModel).order_by(
            AccountOpeningBalanceModel.year, AccountOpeningBalanceModel.account_id
        )
        return [_to_entity(model) for model in self._session.scalars(statement)]

    def save(self, opening: AccountOpeningBalance) -> None:
        statement = select(AccountOpeningBalanceModel).where(
            AccountOpeningBalanceModel.account_id == opening.account_id
        )
        model = self._session.scalars(statement).first()
        if model is None:
            model = AccountOpeningBalanceModel(id=opening.id, account_id=opening.account_id)
            self._session.add(model)
        model.year = opening.year
        model.amount_cents = opening.amount_cents
        self._session.flush()

    def delete(self, account_id: str) -> None:
        self._session.execute(
            delete(AccountOpeningBalanceModel).where(
                AccountOpeningBalanceModel.account_id == account_id
            )
        )
        self._session.flush()
