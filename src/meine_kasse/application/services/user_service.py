"""Pflege der Anwender (ohne Zugangsdaten; diese liegen im AuthService)."""

from collections.abc import Sequence
from dataclasses import replace

from meine_kasse.application.audit import describe_changes
from meine_kasse.application.ports import UnitOfWorkFactory
from meine_kasse.domain.entities import AuditEntry, User
from meine_kasse.domain.errors import DuplicateError, NotFoundError, ValidationError

_USER_FIELDS = ("name", "last_name", "first_name", "address")
_USER_PROTECTED = ("address",)


class UserService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def list_users(self, *, include_inactive: bool = True) -> Sequence[User]:
        with self._uow_factory() as uow:
            users = uow.users.list_all()
        return [user for user in users if include_inactive or user.is_active]

    def get_user(self, user_id: str) -> User:
        with self._uow_factory() as uow:
            user = uow.users.get(user_id)
        if user is None:
            raise NotFoundError("Der Anwender wurde nicht gefunden.")
        return user

    def update_user(
        self,
        user_id: str,
        *,
        name: str,
        last_name: str,
        first_name: str,
        address: str = "",
        actor_id: str | None = None,
    ) -> None:
        name = name.strip()
        if not name:
            raise ValidationError("Der Anmeldename darf nicht leer sein.")
        with self._uow_factory() as uow:
            current = uow.users.get(user_id)
            if current is None:
                raise NotFoundError("Der Anwender wurde nicht gefunden.")
            updated = replace(
                current,
                name=name,
                last_name=last_name.strip(),
                first_name=first_name.strip(),
                address=address.strip(),
            )
            changes = describe_changes(current, updated, _USER_FIELDS, protected=_USER_PROTECTED)
            if changes is None:
                return
            other = uow.users.get_by_name(name)
            if other is not None and other.id != user_id:
                raise DuplicateError(f"Der Anmeldename '{name}' ist bereits vergeben.")
            uow.users.update(updated)
            uow.audit.add(
                AuditEntry(
                    name="USER_UPDATED",
                    entity="users",
                    entity_id=user_id,
                    user_id=actor_id,
                    old_value=changes[0],
                    new_value=changes[1],
                )
            )
            uow.commit()

    def set_active(self, user_id: str, active: bool, *, actor_id: str) -> None:
        """Aktiviert oder deaktiviert einen Anwender.

        Man kann sich nicht selbst deaktivieren, und es bleibt immer mindestens ein aktiver
        Anwender erhalten.
        """
        with self._uow_factory() as uow:
            current = uow.users.get(user_id)
            if current is None:
                raise NotFoundError("Der Anwender wurde nicht gefunden.")
            if current.is_active == active:
                return
            if not active:
                if user_id == actor_id:
                    raise ValidationError("Sie können sich nicht selbst deaktivieren.")
                remaining = [u for u in uow.users.list_all() if u.is_active and u.id != user_id]
                if not remaining:
                    raise ValidationError("Es muss mindestens ein aktiver Anwender bleiben.")
            uow.users.update(replace(current, is_active=active))
            uow.audit.add(
                AuditEntry(
                    name="USER_ACTIVATED" if active else "USER_DEACTIVATED",
                    entity="users",
                    entity_id=user_id,
                    user_id=actor_id,
                    new_value=current.name,
                )
            )
            uow.commit()
