from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from meine_kasse.domain.value_objects.money import parse_euro
from meine_kasse.presentation.dialogs.master_edit_dialog import MasterEditDialog


class QuarterAmountsDialog(MasterEditDialog):
    """Fragt je Quartal einen Betrag ab. Er wird später auf die offenen Monate des Quartals
    verteilt."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Quartalsbeträge", parent)
        info = QLabel(
            "Der Betrag je Quartal wird gleichmäßig auf die offenen Monate des Quartals verteilt. "
            "Ein leeres Feld steht für 0,00 €."
        )
        info.setWordWrap(True)
        self.content.insertWidget(0, info)
        self.edits: dict[int, QLineEdit] = {}
        for quarter in range(1, 5):
            edit = QLineEdit()
            edit.setPlaceholderText("0,00 €")
            self.edits[quarter] = edit
            self.form.addRow(f"{quarter}. Quartal:", edit)
        self.amounts: dict[int, int] = {}

    def save(self) -> None:
        self.amounts = {
            quarter: parse_euro(edit.text()) if edit.text().strip() else 0
            for quarter, edit in self.edits.items()
        }
