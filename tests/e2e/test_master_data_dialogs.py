import os
from collections.abc import Callable, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from meine_kasse.application.services.auth_service import AuthService  # noqa: E402
from meine_kasse.application.services.master_data_service import MasterDataService  # noqa: E402
from meine_kasse.application.services.user_service import UserService  # noqa: E402
from meine_kasse.domain.entities import User  # noqa: E402
from meine_kasse.domain.enums import AccountType, CostCenterKind  # noqa: E402
from meine_kasse.domain.repositories import UnitOfWork  # noqa: E402
from meine_kasse.presentation.dialogs.account_dialogs import (  # noqa: E402
    AccountEditDialog,
    AccountListDialog,
)
from meine_kasse.presentation.dialogs.cost_center_dialogs import (  # noqa: E402
    CostCenterEditDialog,
    CostCenterListDialog,
)
from meine_kasse.presentation.dialogs.master_list_dialog import MasterListDialog  # noqa: E402
from meine_kasse.presentation.dialogs.user_dialogs import (  # noqa: E402
    UserEditDialog,
    UserListDialog,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])  # type: ignore[return-value]


@pytest.fixture(autouse=True)
def actor_user(uow_factory: Callable[[], UnitOfWork]) -> None:
    """Die Dialoge protokollieren den handelnden Anwender; dieser muss existieren."""
    with uow_factory() as uow:
        uow.users.add(
            User(
                id="actor",
                name="actor",
                last_name="",
                first_name="",
                address="",
                password_hash="hash",
                initial_password_hash=None,
                must_change_password=False,
                password_changed_at=None,
            )
        )
        uow.commit()


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Fängt Warnfenster ab, damit Tests nicht auf Benutzereingaben warten."""
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, text: messages.append(text) or None
    )
    yield messages


def _save(dialog: CostCenterEditDialog | AccountEditDialog | UserEditDialog) -> None:
    dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()


def _select_row(dialog: MasterListDialog, row: int) -> None:
    dialog.table.selectRow(row)


def _select_id(dialog: MasterListDialog, entity_id: str) -> int:
    for row in range(dialog.table.rowCount()):
        item = dialog.table.item(row, 0)
        if item is not None and item.data(Qt.ItemDataRole.UserRole) == entity_id:
            dialog.table.selectRow(row)
            return row
    raise AssertionError(f"Zeile {entity_id} nicht gefunden")


def _row_texts(dialog: MasterListDialog) -> list[list[str]]:
    table = dialog.table
    return [
        [table.item(row, column).text() for column in range(table.columnCount())]  # type: ignore[union-attr]
        for row in range(table.rowCount())
    ]


# Kostenstellen


def test_cost_center_dialog_creates_cost_center(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    dialog = CostCenterEditDialog(master_data, "actor")
    dialog.number_edit.setText("100")
    dialog.name_edit.setText("Lebensmittel")
    dialog.valid_from_edit.setDate(QDate(2026, 1, 1))
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData(CostCenterKind.WITHOUT_PLAN.value))
    dialog.notes_edit.setPlainText("Wocheneinkauf")
    _save(dialog)

    (created,) = master_data.list_cost_centers()
    assert (created.number, created.name, created.notes) == ("100", "Lebensmittel", "Wocheneinkauf")
    assert created.kind is CostCenterKind.WITHOUT_PLAN
    assert created.valid_from.isoformat() == "2026-01-01"


def test_cost_center_dialog_shows_duplicate_error_and_stays_open(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    master_data.create_cost_center(number="100", name="A", valid_from=QDate(2026, 1, 1).toPython())
    dialog = CostCenterEditDialog(master_data, "actor")
    dialog.number_edit.setText("100")
    dialog.name_edit.setText("B")
    _save(dialog)

    assert "bereits vergeben" in dialog.error_label.text()
    assert len(master_data.list_cost_centers()) == 1


def test_cost_center_edit_dialog_locks_the_kind(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    cost_center_id = master_data.create_cost_center(
        number="100",
        name="A",
        valid_from=QDate(2026, 1, 1).toPython(),
        kind=CostCenterKind.WITHOUT_PLAN,
    )
    dialog = CostCenterEditDialog(master_data, "actor", cost_center_id)

    assert dialog.number_edit.text() == "100"
    assert dialog.kind_combo.isEnabled() is False
    assert dialog.kind_combo.currentData() == CostCenterKind.WITHOUT_PLAN.value

    dialog.name_edit.setText("Umbenannt")
    _save(dialog)
    assert master_data.get_cost_center(cost_center_id).name == "Umbenannt"


def test_cost_center_list_hides_inactive_until_requested(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    for number, name in (("100", "A"), ("200", "B")):
        master_data.create_cost_center(
            number=number, name=name, valid_from=QDate(2026, 1, 1).toPython()
        )
    dialog = CostCenterListDialog(master_data, "actor")
    assert [row[0] for row in _row_texts(dialog)] == ["100", "200"]
    assert dialog.edit_button.isEnabled() is False

    _select_row(dialog, 0)
    assert dialog.toggle_button.text() == "&Deaktivieren"
    dialog.toggle_button.click()
    assert [row[0] for row in _row_texts(dialog)] == ["200"]

    dialog.show_inactive.setChecked(True)
    rows = _row_texts(dialog)
    assert [row[0] for row in rows] == ["100", "200"]
    assert rows[0][-1] == "Inaktiv"

    _select_row(dialog, 0)
    assert dialog.toggle_button.text() == "&Aktivieren"
    dialog.toggle_button.click()
    assert _row_texts(dialog)[0][-1] == "Aktiv"


def test_list_rows_carry_the_entity_id(qapp: QApplication, master_data: MasterDataService) -> None:
    cost_center_id = master_data.create_cost_center(
        number="100", name="A", valid_from=QDate(2026, 1, 1).toPython()
    )
    dialog = CostCenterListDialog(master_data, "actor")
    _select_row(dialog, 0)
    assert dialog.selected_id() == cost_center_id
    item = dialog.table.item(0, 0)
    assert item is not None
    assert item.data(Qt.ItemDataRole.UserRole) == cost_center_id


# Konten


def test_account_dialog_creates_and_edits_account(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    dialog = AccountEditDialog(master_data, "actor")
    dialog.number_edit.setText("1000")
    dialog.name_edit.setText("Girokonto")
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(AccountType.SAVINGS.value))
    dialog.owner_edit.setText("Anna Muster")
    dialog.iban_edit.setText("DE89 3704 0044 0532 0130 00")
    _save(dialog)

    (account,) = master_data.list_accounts()
    assert account.iban == "DE89370400440532013000"
    assert account.account_type is AccountType.SAVINGS

    edit = AccountEditDialog(master_data, "actor", account.id)
    assert edit.iban_edit.text() == "DE89 3704 0044 0532 0130 00"
    edit.iban_edit.setText("DE00")
    _save(edit)
    assert "IBAN" in edit.error_label.text()
    assert master_data.get_account(account.id).iban == "DE89370400440532013000"


def test_account_list_shows_german_labels_and_formatted_iban(
    qapp: QApplication, master_data: MasterDataService
) -> None:
    master_data.create_account(
        number="1000",
        name="Girokonto",
        account_type=AccountType.CHECKING,
        iban="DE89370400440532013000",
    )
    dialog = AccountListDialog(master_data, "actor")
    (row,) = _row_texts(dialog)
    assert row[:3] == ["1000", "Girokonto", "Giro"]
    assert row[4] == "DE89 3704 0044 0532 0130 00"


# Anwender


@pytest.fixture
def admin_id(auth: AuthService) -> str:
    return auth.create_user(
        name="admin", last_name="Admin", first_name="", initial_password="Erstpasswort-1"
    )


def test_user_dialog_creates_user_with_forced_password_change(
    qapp: QApplication, auth: AuthService, users: UserService, admin_id: str
) -> None:
    dialog = UserEditDialog(auth, users, admin_id)
    dialog.name_edit.setText("berta")
    dialog.password_edit.setText("Erstpasswort-2")
    dialog.repeat_edit.setText("Anders-12345")
    _save(dialog)
    assert "stimmen nicht überein" in dialog.error_label.text()

    dialog.repeat_edit.setText("Erstpasswort-2")
    _save(dialog)
    assert auth.login("berta", "Erstpasswort-2").must_change_password is True


def test_user_list_blocks_self_deactivation_with_a_warning(
    qapp: QApplication,
    auth: AuthService,
    users: UserService,
    admin_id: str,
    warnings: list[str],
) -> None:
    auth.create_user(name="berta", last_name="", first_name="", initial_password="Erstpasswort-2")
    dialog = UserListDialog(auth, users, admin_id)
    _select_id(dialog, admin_id)
    assert dialog.selected_id() == admin_id

    dialog.toggle_button.click()

    assert warnings and "selbst" in warnings[0]
    assert users.get_user(admin_id).is_active is True


def test_user_list_password_actions_follow_selection(
    qapp: QApplication, auth: AuthService, users: UserService, admin_id: str
) -> None:
    dialog = UserListDialog(auth, users, admin_id)
    assert dialog.reset_button.isEnabled() is False
    row = _select_id(dialog, admin_id)
    assert dialog.reset_button.isEnabled() is True
    assert _row_texts(dialog)[row][3] == "Wechsel erforderlich"
