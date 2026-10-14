from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meine_kasse.infrastructure.database.models import UserSettingModel


class SqlUserSettingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: str, key: str) -> str | None:
        model = self._find(user_id, key)
        return None if model is None else model.value_json

    def save(self, user_id: str, key: str, value_json: str) -> None:
        model = self._find(user_id, key)
        if model is None:
            model = UserSettingModel(user_id=user_id, name=key)
            self._session.add(model)
        model.value_json = value_json
        self._session.flush()

    def delete(self, user_id: str, key: str) -> None:
        self._session.execute(
            delete(UserSettingModel).where(
                UserSettingModel.user_id == user_id, UserSettingModel.name == key
            )
        )
        self._session.flush()

    def _find(self, user_id: str, key: str) -> UserSettingModel | None:
        statement = select(UserSettingModel).where(
            UserSettingModel.user_id == user_id, UserSettingModel.name == key
        )
        return self._session.scalars(statement).first()
