"""PDF-Ausgabe aus der Oberfläche: Zusatz zum Dateinamen abfragen, ablegen, öffnen."""

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from meine_kasse.application.reporting.pdf_model import PdfTable
from meine_kasse.application.services.document_service import DocumentService, DocumentView
from meine_kasse.domain.enums import DocumentType
from meine_kasse.domain.errors import DomainError
from meine_kasse.domain.services.document_rules import MAX_SUFFIX_LENGTH

logger = logging.getLogger("meine_kasse.pdf")
_TITLE = "PDF-Ausgabe"


def open_in_system(path: Path) -> bool:
    """Öffnet die Datei im PDF-Programm des Systems."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class PdfExporter:
    """Erzeugt PDF-Dateien für den angemeldeten Anwender und legt sie im Archiv ab."""

    def __init__(self, documents: DocumentService, user_id: str) -> None:
        self._documents = documents
        self._user_id = user_id

    @property
    def documents(self) -> DocumentService:
        return self._documents

    def ask_suffix(self, parent: QWidget | None) -> str | None:
        """Fragt den manuellen Zusatz ab. `None` bedeutet Abbruch."""
        dialog = QInputDialog(parent)
        dialog.setWindowTitle(_TITLE)
        dialog.setLabelText(
            f"Zusatz für den Dateinamen (optional, höchstens {MAX_SUFFIX_LENGTH} Zeichen):"
        )
        dialog.setOkButtonText("PDF erstellen")
        dialog.setCancelButtonText("Abbrechen")
        editor = dialog.findChild(QLineEdit)
        if editor is not None:
            editor.setMaxLength(MAX_SUFFIX_LENGTH)
        if dialog.exec() != QInputDialog.DialogCode.Accepted:
            return None
        return dialog.textValue()

    def export(
        self,
        parent: QWidget | None,
        table: PdfTable,
        document_type: DocumentType = DocumentType.TABLE,
    ) -> DocumentView | None:
        return self.export_with(
            parent,
            lambda suffix: self._documents.create_pdf(
                table, document_type=document_type, suffix=suffix, actor_id=self._user_id
            ),
        )

    def export_with(
        self, parent: QWidget | None, create: Callable[[str], DocumentView]
    ) -> DocumentView | None:
        """Fragt den Zusatz ab, erzeugt das PDF über `create(suffix)` und bietet das Öffnen an."""
        suffix = self.ask_suffix(parent)
        if suffix is None:
            return None
        try:
            view = create(suffix)
        except DomainError as error:
            QMessageBox.warning(parent, _TITLE, str(error))
            return None
        except Exception:  # noqa: BLE001 - die Oberfläche zeigt nur eine allgemeine Meldung
            logger.exception("Die PDF-Datei konnte nicht erstellt werden")
            QMessageBox.critical(
                parent,
                _TITLE,
                "Die PDF-Datei konnte nicht erstellt werden. Details stehen in der Protokolldatei.",
            )
            return None
        self.offer_open(parent, view)
        return view

    def offer_open(self, parent: QWidget | None, view: DocumentView) -> None:
        answer = QMessageBox.question(
            parent,
            _TITLE,
            f"Das PDF wurde im Dokumentenarchiv abgelegt:\n{view.file_name}\n\nJetzt öffnen?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.open_document(parent, view.id)

    def open_document(self, parent: QWidget | None, document_id: str) -> None:
        try:
            path = self._documents.path_of(document_id)
        except DomainError as error:
            QMessageBox.warning(parent, _TITLE, str(error))
            return
        if not open_in_system(path):
            QMessageBox.warning(
                parent,
                _TITLE,
                f"Die Datei konnte nicht geöffnet werden. Sie liegt hier:\n{path}",
            )
