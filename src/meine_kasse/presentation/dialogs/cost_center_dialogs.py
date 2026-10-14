from collections.abc import Sequence
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from meine_kasse.application.services.master_data_service import MasterDataService
from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog
from meine_kasse.presentation.dialogs.master_list_dialog import ListRow, MasterListDialog
from meine_kasse.presentation.labels import COST_CENTER_KIND_LABELS, format_date
from meine_kasse.presentation.widgets.data_table import TablePreferences


class CostCenterEditDialog(MasterEditDialog):
    def __init__(
        self,
        service: MasterDataService,
        actor_id: str,
        cost_center_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Kostenstelle bearbeiten" if cost_center_id else "Neue Kostenstelle", parent
        )
        self._service = service
        self._actor_id = actor_id
        self._cost_center_id = cost_center_id

        self.number_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.valid_from_edit = QDateEdit(QDate.currentDate())
        self.valid_from_edit.setCalendarPopup(True)
        self.valid_from_edit.setDisplayFormat("dd.MM.yyyy")
        self.kind_combo = QComboBox()
        for kind, label in COST_CENTER_KIND_LABELS.items():
            self.kind_combo.addItem(label, kind.value)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(80)

        self.form.addRow("Nummer:", self.number_edit)
        self.form.addRow("Name:", self.name_edit)
        self.form.addRow("Kostenstelle ab:", self.valid_from_edit)
        self.form.addRow("Art:", self.kind_combo)
        self.form.addRow("Bemerkungen:", self.notes_edit)

        if cost_center_id is not None:
            current = service.get_cost_center(cost_center_id)
            self.number_edit.setText(current.number)
            self.name_edit.setText(current.name)
            self.valid_from_edit.setDate(
                QDate(current.valid_from.year, current.valid_from.month, current.valid_from.day)
            )
            self.kind_combo.setCurrentIndex(self.kind_combo.findData(current.kind.value))
            self.kind_combo.setEnabled(False)
            self.notes_edit.setPlainText(current.notes)
            hint = QLabel("Die Art kann nach dem Anlegen nicht mehr geändert werden.")
            hint.setStyleSheet("color: #606060;")
            self.form.addRow("", hint)

    def save(self) -> None:
        qdate = self.valid_from_edit.date()
        valid_from = date(qdate.year(), qdate.month(), qdate.day())
        notes = self.notes_edit.toPlainText()
        if self._cost_center_id is None:
            kind = CostCenterKind(self.kind_combo.currentData())
            self._service.create_cost_center(
                number=self.number_edit.text(),
                name=self.name_edit.text(),
                valid_from=valid_from,
                kind=kind,
                notes=notes,
                actor_id=self._actor_id,
            )
        else:
            self._service.update_cost_center(
                self._cost_center_id,
                number=self.number_edit.text(),
                name=self.name_edit.text(),
                valid_from=valid_from,
                notes=notes,
                actor_id=self._actor_id,
            )


class CostCenterListDialog(MasterListDialog):
    def __init__(
        self,
        service: MasterDataService,
        actor_id: str,
        parent: QWidget | None = None,
        *,
        preferences: TablePreferences | None = None,
    ) -> None:
        super().__init__(
            "Kostenstellen", ["Nummer", "Name", "Art", "Ab"], parent, preferences=preferences
        )
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
                    COST_CENTER_KIND_LABELS[item.kind],
                    format_date(item.valid_from),
                ],
                active=item.is_active,
            )
            for item in self._service.list_cost_centers(include_inactive=include_inactive)
        ]

    def open_editor(self, entity_id: str | None) -> bool:
        dialog = CostCenterEditDialog(self._service, self._actor_id, entity_id, self)
        return bool(dialog.exec())

    def apply_active(self, entity_id: str, active: bool) -> None:
        self._service.set_cost_center_active(entity_id, active, actor_id=self._actor_id)
