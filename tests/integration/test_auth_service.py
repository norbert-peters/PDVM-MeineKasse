from datetime import UTC, datetime

import pytest

from meine_kasse.application.services.auth_service import (
    LOGIN_FAILED_MESSAGE,
    AuthService,
)
from meine_kasse.domain.errors import (
    AuthenticationError,
    DuplicateError,
    ValidationError,
)
from meine_kasse.infrastructure.database.models import AuditLogModel, UserModel
from meine_kasse.infrastructure.database.session import Database
from meine_kasse.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from meine_kasse.infrastructure.security.password_hasher import Argon2PasswordHasher

INITIAL = "Erstpasswort-1"


@pytest.fixture
def user_id(auth: AuthService) -> str:
    return auth.create_user(
        name="anna", last_name="Muster", first_name="Anna", initial_password=INITIAL
    )


def test_no_users_initially(auth: AuthService) -> None:
    assert auth.has_users() is False


def test_password_is_stored_as_argon2id_hash_only(
    auth: AuthService, database: Database, user_id: str
) -> None:
    with database.session_factory() as session:
        model = session.get(UserModel, user_id)
        assert model is not None
        assert model.password_hash.startswith("$argon2id$")
        assert INITIAL not in model.password_hash
        assert model.initial_password_hash is not None
        assert model.initial_password_hash.startswith("$argon2id$")
        assert model.must_change_password is True


def test_first_login_requires_password_change(auth: AuthService, user_id: str) -> None:
    result = auth.login("anna", INITIAL)
    assert result.user_id == user_id
    assert result.must_change_password is True
    assert result.display_name == "Anna Muster"


def test_login_is_case_insensitive_for_name(auth: AuthService, user_id: str) -> None:
    assert auth.login("ANNA", INITIAL).user_id == user_id


@pytest.mark.parametrize(
    ("name", "password"), [("anna", "falsch-falsch"), ("unbekannt", INITIAL), ("", "")]
)
def test_login_failures_share_one_message(
    auth: AuthService, user_id: str, name: str, password: str
) -> None:
    with pytest.raises(AuthenticationError) as error:
        auth.login(name, password)
    assert str(error.value) == LOGIN_FAILED_MESSAGE


def test_inactive_user_gets_same_failure_message(
    auth: AuthService, database: Database, user_id: str
) -> None:
    with database.session_factory() as session:
        session.get(UserModel, user_id).is_active = False  # type: ignore[union-attr]
        session.commit()
    with pytest.raises(AuthenticationError) as error:
        auth.login("anna", INITIAL)
    assert str(error.value) == LOGIN_FAILED_MESSAGE


def test_change_password_clears_flag_and_sets_timestamp(database: Database, user_id: str) -> None:
    fixed = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    service = AuthService(
        lambda: SqlAlchemyUnitOfWork(database.session_factory),
        Argon2PasswordHasher(),
        clock=lambda: fixed,
    )
    service.change_password(user_id, INITIAL, "Neues-Passwort-2")

    result = service.login("anna", "Neues-Passwort-2")
    assert result.must_change_password is False
    with database.session_factory() as session:
        model = session.get(UserModel, user_id)
        assert model is not None
        assert model.password_changed_at == fixed
    with pytest.raises(AuthenticationError):
        service.login("anna", INITIAL)


def test_change_password_rules(auth: AuthService, user_id: str) -> None:
    with pytest.raises(AuthenticationError):
        auth.change_password(user_id, "falsch-falsch", "Neues-Passwort-2")
    with pytest.raises(ValidationError):
        auth.change_password(user_id, INITIAL, "kurz")
    with pytest.raises(ValidationError):
        auth.change_password(user_id, INITIAL, INITIAL)


def test_user_cannot_pick_the_initial_password_again(auth: AuthService, user_id: str) -> None:
    auth.change_password(user_id, INITIAL, "Neues-Passwort-2")
    with pytest.raises(ValidationError):
        auth.change_password(user_id, "Neues-Passwort-2", INITIAL)


def test_reset_restores_initial_password_and_forces_change(auth: AuthService, user_id: str) -> None:
    auth.change_password(user_id, INITIAL, "Neues-Passwort-2")
    auth.reset_to_initial_password(user_id, actor_id=user_id)

    result = auth.login("anna", INITIAL)
    assert result.must_change_password is True
    with pytest.raises(AuthenticationError):
        auth.login("anna", "Neues-Passwort-2")


def test_set_initial_password_replaces_current_password(auth: AuthService, user_id: str) -> None:
    auth.change_password(user_id, INITIAL, "Neues-Passwort-2")
    auth.set_initial_password(user_id, "Anderes-Start-3", actor_id=user_id)

    assert auth.login("anna", "Anderes-Start-3").must_change_password is True
    with pytest.raises(AuthenticationError):
        auth.login("anna", INITIAL)


def test_duplicate_user_name_is_rejected(auth: AuthService, user_id: str) -> None:
    with pytest.raises(DuplicateError):
        auth.create_user(
            name="ANNA", last_name="Zwei", first_name="Anna", initial_password="Anderes-Start-3"
        )


def test_initial_password_must_follow_policy(auth: AuthService) -> None:
    with pytest.raises(ValidationError):
        auth.create_user(name="bernd", last_name="", first_name="", initial_password="kurz")


def test_audit_log_has_no_secrets(auth: AuthService, database: Database, user_id: str) -> None:
    auth.change_password(user_id, INITIAL, "Neues-Passwort-2")
    with database.session_factory() as session:
        entries = session.query(AuditLogModel).all()
    names = {entry.name for entry in entries}
    assert {"USER_CREATED", "PASSWORD_CHANGED"} <= names
    for entry in entries:
        for value in (entry.old_value, entry.new_value):
            assert value is None or ("argon2" not in value and "Passwort" not in value)
