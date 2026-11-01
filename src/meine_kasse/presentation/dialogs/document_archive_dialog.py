from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from meine_kasse.application.services.document_service import DocumentState, DocumentView
from meine_kasse.domain.errors import DomainError
from meine_kasse.presentation.labels import DOCUMENT_TYPE_LABELS
from meine_kasse.presentation.widgets.data_table import (
    AUTO,
    DataTable,
    SortItem,
    TablePreferences,
)
from meine_kasse.presentation.widgets.pdf_export import PdfExporter, open_in_system

_COLUMNS = ["Erstellt", "Titel", "Dateiname", "Art", "Ersteller", "Größe", "Status"]
_SIZE_COLUMN = 5
_MISSING = QBrush(QColor("#b00020"))
_STATE_TEXT = {
    DocumentState.OK: "Datei unverändert",
    DocumentState.MISSING: "Datei fehlt",
    DocumentState.CHANGED: "Datei verändert",
}
_KILOBYTE = 1024


def format_size(size_bytes: int) -> str:
    if size_bytes < _KILOBYTE:
        return f"{size_bytes} Byte"
    kilobytes = size_bytes / _KILOBYTE
    if kilobytes < _KILOBYTE:
        return f"{kilobytes:.1f} KB".replace(".", ",")
    return f"{kilobytes / _KILOBYTE:.1f} MB".replace(".", ",")


class DocumentArchiveDialog(QDialog):
    """Dokumentenarchiv: alle erzeugten PDF-Dateien, durchsuch- und sortierbar."""

    def __init__(
        self,
        exporter: PdfExporter,
        parent: QWidget | None = None,
        *,
        preferences: TablePreferences | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dokumentenarchiv")
        self.resize(1100, 480)
        self._exporter = exporter
        self._documents = exporter.documents

        self.data_table = DataTable(_COLUMNS, table_key="documents", preferences=preferences)
        self.table = self.data_table.table
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda _item: self._open())

        self.info_label = QLabel(f"Ablage: {self._documents.directory}")
        self.info_label.setStyleSheet("color: #606060;")
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.open_button = self._button("&Öffnen", self._open)
        self.verify_button = self._button("&Prüfen", self._verify)
        self.folder_button = self._button("&Ordner öffnen", self._open_folder)
        close_button = self._button("&Schließen", self.accept)

        buttons = QHBoxLayout()
        for button in (self.open_button, self.verify_button, self.folder_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.data_table)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)
        self.refresh()

    def _button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: handler())
        return button

    def selected_id(self) -> str | None:
        return self.data_table.selected_id()

    def refresh(self) -> None:
        keep = self.selected_id()
        try:
            documents = self._documents.list_documents()
        except DomainError as error:
            self.message_label.setText(str(error))
            return
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            self._fill_row(row, document)
        self.data_table.apply()
        self.data_table.select_id(keep)
        self._update_buttons()

    def _fill_row(self, row: int, document: DocumentView) -> None:
        created = document.created_at.astimezone()
        cells: list[tuple[str, object]] = [
            (f"{created:%d.%m.%Y %H:%M}", created.timestamp()),
            (document.name, AUTO),
            (document.file_name, AUTO),
            (DOCUMENT_TYPE_LABELS[document.document_type], AUTO),
            (document.created_by, AUTO),
            (format_size(document.size_bytes), document.size_bytes),
            ("vorhanden" if document.exists else "Datei fehlt", AUTO),
        ]
        for column, (text, sort_value) in enumerate(cells):
            item = SortItem(text, sort_value=sort_value, row_id=document.id)
            if column == _SIZE_COLUMN:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if not document.exists:
                item.setForeground(_MISSING)
            self.table.setItem(row, column, item)

    def _update_buttons(self) -> None:
        has_selection = self.selected_id() is not None
        self.open_button.setEnabled(has_selection)
        self.verify_button.setEnabled(has_selection)

    def _open(self) -> None:
        selected = self.selected_id()
        if selected is not None:
            self._exporter.open_document(self, selected)

    def _verify(self) -> None:
        selected = self.selected_id()
        if selected is None:
            return
        try:
            state = self._documents.verify(selected)
        except DomainError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self.message_label.setText(_STATE_TEXT[state])
        self.message_label.setStyleSheet("" if state is DocumentState.OK else "color: #b00020;")

    def _open_folder(self) -> None:
        directory = self._documents.directory
        directory.mkdir(parents=True, exist_ok=True)
        if not open_in_system(directory):
            QMessageBox.warning(self, self.windowTitle(), f"Der Ordner liegt hier:\n{directory}")
