"""Anmeldung und Passwortverwaltung (siehe Entwicklungsregeln, Abschnitt 5)."""

from dataclasses import dataclass, replace

from meine_kasse.application.ports import Clock, PasswordHasher, UnitOfWorkFactory, utc_now
from meine_kasse.domain.entities import AuditEntry, User
from meine_kasse.domain.errors import (
    AuthenticationError,
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from meine_kasse.domain.identifiers import new_id
from meine_kasse.domain.services.password_policy import validate_new_password

LOGIN_FAILED_MESSAGE = "Anmeldename oder Passwort ist falsch."


@dataclass(frozen=True, slots=True)
class LoginResult:
    user_id: str
    display_name: str
    must_change_password: bool


class AuthService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        clock: Clock = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._clock = clock
        self._dummy_hash: str | None = None

    def has_users(self) -> bool:
        with self._uow_factory() as uow:
            return uow.users.count() > 0

    def create_user(
        self,
        *,
        name: str,
        last_name: str,
        first_name: str,
        address: str = "",
        initial_password: str,
        actor_id: str | None = None,
    ) -> str:
        """Legt einen Anwender an. Das erstmalige Passwort muss bei der ersten Anmeldung
        geändert werden."""
        name = name.strip()
        if not name:
            raise ValidationError("Der Anmeldename darf nicht leer sein.")
        validate_new_password(initial_password)

        initial_hash = self._hasher.hash(initial_password)
        user = User(
            id=new_id(),
            name=name,
            last_name=last_name.strip(),
            first_name=first_name.strip(),
            address=address.strip(),
            password_hash=initial_hash,
            initial_password_hash=initial_hash,
            must_change_password=True,
            password_changed_at=None,
        )
        with self._uow_factory() as uow:
            if uow.users.get_by_name(name) is not None:
                raise DuplicateError(f"Der Anmeldename '{name}' ist bereits vergeben.")
            uow.users.add(user)
            uow.audit.add(
                AuditEntry(
                    name="USER_CREATED",
                    entity="users",
                    entity_id=user.id,
                    user_id=actor_id,
                    new_value=name,
                )
            )
            uow.commit()
        return user.id

    def login(self, name: str, password: str) -> LoginResult:
        """Meldet an. Unbekannter Anwender, gesperrter Anwender und falsches Passwort liefern
        dieselbe Meldung."""
        with self._uow_factory() as uow:
            user = uow.users.get_by_name(name)
            if user is None or not user.is_active:
                self._hasher.verify(self._get_dummy_hash(), password)
                raise AuthenticationError(LOGIN_FAILED_MESSAGE)
            if not self._hasher.verify(user.password_hash, password):
                raise AuthenticationError(LOGIN_FAILED_MESSAGE)
            if self._hasher.needs_rehash(user.password_hash):
                uow.users.update(replace(user, password_hash=self._hasher.hash(password)))
                uow.commit()
            return LoginResult(user.id, user.display_name, user.must_change_password)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        validate_new_password(new_password)
        with self._uow_factory() as uow:
            user = self._get_user(uow.users.get(user_id))
            if not self._hasher.verify(user.password_hash, old_password):
                raise AuthenticationError("Das bisherige Passwort ist falsch.")
            if new_password == old_password:
                raise ValidationError("Das neue Passwort muss sich vom bisherigen unterscheiden.")
            if user.initial_password_hash and self._hasher.verify(
                user.initial_password_hash, new_password
            ):
                raise ValidationError("Das neue Passwort darf nicht das erstmalige Passwort sein.")
            uow.users.update(
                replace(
                    user,
                    password_hash=self._hasher.hash(new_password),
                    must_change_password=False,
                    password_changed_at=self._clock(),
                )
            )
            uow.audit.add(
                AuditEntry(
                    name="PASSWORD_CHANGED",
                    entity="users",
                    entity_id=user.id,
                    user_id=user.id,
                )
            )
            uow.commit()

    def set_initial_password(self, user_id: str, initial_password: str, actor_id: str) -> None:
        """Legt ein neues erstmaliges Passwort fest und setzt das aktuelle Passwort darauf."""
        validate_new_password(initial_password)
        initial_hash = self._hasher.hash(initial_password)
        with self._uow_factory() as uow:
            user = self._get_user(uow.users.get(user_id))
            uow.users.update(
                replace(
                    user,
                    password_hash=initial_hash,
                    initial_password_hash=initial_hash,
                    must_change_password=True,
                )
            )
            uow.audit.add(
                AuditEntry(
                    name="INITIAL_PASSWORD_SET",
                    entity="users",
                    entity_id=user.id,
                    user_id=actor_id,
                )
            )
            uow.commit()

    def reset_to_initial_password(self, user_id: str, actor_id: str) -> None:
        """Setzt das Passwort auf das erstmalige Passwort zurück; der Wechsel ist dann Pflicht."""
        with self._uow_factory() as uow:
            user = self._get_user(uow.users.get(user_id))
            if user.initial_password_hash is None:
                raise ValidationError(
                    "Für diesen Anwender ist kein erstmaliges Passwort hinterlegt."
                )
            uow.users.update(
                replace(
                    user,
                    password_hash=user.initial_password_hash,
                    must_change_password=True,
                )
            )
            uow.audit.add(
                AuditEntry(
                    name="PASSWORD_RESET",
                    entity="users",
                    entity_id=user.id,
                    user_id=actor_id,
                )
            )
            uow.commit()

    @staticmethod
    def _get_user(user: User | None) -> User:
        if user is None:
            raise NotFoundError("Der Anwender wurde nicht gefunden.")
        return user

    def _get_dummy_hash(self) -> str:
        """Gleicht die Antwortzeit bei unbekanntem Anwender an."""
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash("kein-anwender")
        return self._dummy_hash
