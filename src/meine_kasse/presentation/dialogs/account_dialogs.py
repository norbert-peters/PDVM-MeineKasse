from collections.abc import Sequence

from PySide6.QtWidgets import QComboBox, QLineEdit, QWidget

from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import AccountType
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.dialogs.master_list_dialog import ListRow, MasterListDialog
from meine_kasse.presentation.labels import ACCOUNT_TYPE_LABELS, format_iban


class AccountEditDialog(MasterEditDialog):
    def __init__(
        self,
        service: MasterDataService,
        actor_id: str,
        account_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Konto bearbeiten" if account_id else "Neues Konto", parent)
        self._service = service
        self._actor_id = actor_id
        self._account_id = account_id

        self.number_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        for account_type, label in ACCOUNT_TYPE_LABELS.items():
            self.type_combo.addItem(label, account_type.value)
        self.bank_edit = QLineEdit()
        self.owner_edit = QLineEdit()
        self.iban_edit = QLineEdit()

        self.form.addRow("Kontonummer:", self.number_edit)
        self.form.addRow("Bezeichnung:", self.name_edit)
        self.form.addRow("Kontoart:", self.type_combo)
        self.form.addRow("Bank:", self.bank_edit)
        self.form.addRow("Kontoinhaber:", self.owner_edit)
        self.form.addRow("IBAN:", self.iban_edit)

        if account_id is not None:
            current = service.get_account(account_id)
            self.number_edit.setText(current.number)
            self.name_edit.setText(current.name)
            self.type_combo.setCurrentIndex(self.type_combo.findData(current.account_type.value))
            self.bank_edit.setText(current.bank_name)
            self.owner_edit.setText(current.owner_name)
            self.iban_edit.setText(format_iban(current.iban))

    def save(self) -> None:
        account_type = AccountType(self.type_combo.currentData())
        if self._account_id is None:
            self._service.create_account(
                number=self.number_edit.text(),
                name=self.name_edit.text(),
                account_type=account_type,
                bank_name=self.bank_edit.text(),
                owner_name=self.owner_edit.text(),
                iban=self.iban_edit.text(),
                actor_id=self._actor_id,
            )
        else:
            self._service.update_account(
                self._account_id,
                number=self.number_edit.text(),
                name=self.name_edit.text(),
                account_type=account_type,
                bank_name=self.bank_edit.text(),
                owner_name=self.owner_edit.text(),
                iban=self.iban_edit.text(),
                actor_id=self._actor_id,
            )


class AccountListDialog(MasterListDialog):
    def __init__(
        self, service: MasterDataService, actor_id: str, parent: QWidget | None = None
    ) -> None:
        super().__init__("Konten", ["Nummer", "Bezeichnung", "Kontoart", "Inhaber", "IBAN"], parent)
        self._service = service
        self._actor_id = actor_id
        self.refresh()

    def load_rows(self, include_inactive: bool) -> Sequence[ListRow]:
        return [
            ListRow(
                id=item.id,
                cells=[
                    item.number,
                    item.name,
                    ACCOUNT_TYPE_LABELS[item.account_type],
                    item.owner_name,
                    format_iban(item.iban),
                ],
                active=item.is_active,
            )
            for item in self._service.list_accounts(include_inactive=include_inactive)
        ]

    def open_editor(self, entity_id: str | None) -> bool:
        dialog = AccountEditDialog(self._service, self._actor_id, entity_id, self)
        return bool(dialog.exec())

    def apply_active(self, entity_id: str, active: bool) -> None:
        self._service.set_account_active(entity_id, active, actor_id=self._actor_id)
