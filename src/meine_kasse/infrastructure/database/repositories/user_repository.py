from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import User
from meine_kasse.infrastructure.database.models import UserModel


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        name=model.name,
        last_name=model.last_name,
        first_name=model.first_name,
        address=model.address,
        password_hash=model.password_hash,
        initial_password_hash=model.initial_password_hash,
        must_change_password=model.must_change_password,
        password_changed_at=model.password_changed_at,
        is_active=model.is_active,
    )


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                name=user.name,
                last_name=user.last_name,
                first_name=user.first_name,
                address=user.address,
                password_hash=user.password_hash,
                initial_password_hash=user.initial_password_hash,
                must_change_password=user.must_change_password,
                password_changed_at=user.password_changed_at,
                is_active=user.is_active,
            )
        )
        self._session.flush()

    def update(self, user: User) -> None:
        model = self._session.get(UserModel, user.id)
        if model is None:
            raise LookupError(f"Anwender {user.id} existiert nicht.")
        model.name = user.name
        model.last_name = user.last_name
        model.first_name = user.first_name
        model.address = user.address
        model.password_hash = user.password_hash
        model.initial_password_hash = user.initial_password_hash
        model.must_change_password = user.must_change_password
        model.password_changed_at = user.password_changed_at
        model.is_active = user.is_active
        self._session.flush()

    def get(self, user_id: str) -> User | None:
        model = self._session.get(UserModel, user_id)
        return None if model is None else _to_entity(model)

    def get_by_name(self, name: str) -> User | None:
        statement = select(UserModel).where(func.lower(UserModel.name) == name.strip().lower())
        model = self._session.scalars(statement).first()
        return None if model is None else _to_entity(model)

    def list_all(self) -> Sequence[User]:
        statement = select(UserModel).order_by(func.lower(UserModel.name))
        return [_to_entity(model) for model in self._session.scalars(statement)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(UserModel)) or 0
