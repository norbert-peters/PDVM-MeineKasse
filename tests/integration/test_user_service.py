import pytest
from sqlalchemy import select

from meine_kasse.application.services.auth_service import AuthService
from meine_kasse.application.services.user_service import UserService
from meine_kasse.domain.errors import AuthenticationError, DuplicateError, ValidationError
from meine_kasse.infrastructure.database.models import AuditLogModel
from meine_kasse.infrastructure.database.session import Database

INITIAL = "Erstpasswort-1"


@pytest.fixture
def admin_id(auth: AuthService) -> str:
    return auth.create_user(
        name="admin", last_name="Admin", first_name="", initial_password=INITIAL
    )


@pytest.fixture
def other_id(auth: AuthService) -> str:
    return auth.create_user(
        name="berta", last_name="Beispiel", first_name="Berta", initial_password=INITIAL
    )


def test_update_user_changes_names_and_hides_address_in_audit(
    users: UserService, database: Database, other_id: str
) -> None:
    users.update_user(
        other_id,
        name="berta2",
        last_name="Neu",
        first_name="Berta",
        address="Musterweg 1, 12345 Musterstadt",
        actor_id=other_id,
    )

    updated = users.get_user(other_id)
    assert (updated.name, updated.last_name) == ("berta2", "Neu")
    with database.session_factory() as session:
        entries = list(
            session.scalars(select(AuditLogModel).where(AuditLogModel.name == "USER_UPDATED"))
        )
    (entry,) = entries
    assert "Musterweg" not in f"{entry.old_value} {entry.new_value}"


def test_update_user_rejects_duplicate_name_but_allows_own_name(
    users: UserService, admin_id: str, other_id: str
) -> None:
    with pytest.raises(DuplicateError):
        users.update_user(other_id, name="ADMIN", last_name="", first_name="")
    users.update_user(other_id, name="BERTA", last_name="B", first_name="B")


def test_deactivated_user_cannot_log_in(
    auth: AuthService, users: UserService, admin_id: str, other_id: str
) -> None:
    users.set_active(other_id, False, actor_id=admin_id)
    with pytest.raises(AuthenticationError):
        auth.login("berta", INITIAL)

    users.set_active(other_id, True, actor_id=admin_id)
    assert auth.login("berta", INITIAL).user_id == other_id


def test_user_cannot_deactivate_themselves(
    users: UserService, admin_id: str, other_id: str
) -> None:
    with pytest.raises(ValidationError, match="selbst"):
        users.set_active(admin_id, False, actor_id=admin_id)


def test_last_active_user_stays_active(users: UserService, admin_id: str, other_id: str) -> None:
    users.set_active(other_id, False, actor_id=admin_id)
    with pytest.raises(ValidationError, match="mindestens ein aktiver"):
        users.set_active(admin_id, False, actor_id=other_id)


def test_list_users_can_hide_inactive(users: UserService, admin_id: str, other_id: str) -> None:
    users.set_active(other_id, False, actor_id=admin_id)
    assert [u.name for u in users.list_users(include_inactive=False)] == ["admin"]
    assert [u.name for u in users.list_users()] == ["admin", "berta"]
