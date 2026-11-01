import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import World
from meine_kasse.application.reporting.pdf_model import PdfColumn, PdfRow, PdfTable, RowStyle
from meine_kasse.application.services.document_service import DocumentService, DocumentState
from meine_kasse.domain.enums import DocumentType
from meine_kasse.domain.errors import NotFoundError, ValidationError
from meine_kasse.domain.repositories import UnitOfWork
from meine_kasse.infrastructure.reporting.pdf_renderer import ReportlabPdfRenderer

NOW = datetime(2026, 5, 15, 12, 30, 5, tzinfo=UTC)
LOCAL_STAMP = NOW.astimezone().strftime("%Y-%m-%d_%H%M%S")

TABLE = PdfTable(
    title="Buchungen",
    columns=(PdfColumn("Datum"), PdfColumn("Betrag", align_right=True)),
    rows=(
        PdfRow(("01.05.2026", "-12,50 €")),
        PdfRow(("Summe Mai → Ä Ö Ü ß", "1.234,56 €"), RowStyle.SUBTOTAL),
    ),
    subtitle_lines=("Zeitraum: Mai 2026", "2 Zeilen"),
    total_row=PdfRow(("Gesamt", "1.222,06 €"), RowStyle.TOTAL),
)


class FakeRenderer:
    def __init__(self, content: bytes = b"%PDF-fake") -> None:
        self.content = content
        self.calls = 0

    def render(self, table: PdfTable, target: Path) -> None:
        self.calls += 1
        target.write_bytes(self.content)


class FailingRenderer:
    def render(self, table: PdfTable, target: Path) -> None:
        target.write_bytes(b"halb fertig")
        raise RuntimeError("Absturz beim Rendern")


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    return tmp_path / "Dokumente"


@pytest.fixture
def documents(
    uow_factory: Callable[[], UnitOfWork], archive: Path, world: World
) -> DocumentService:
    return DocumentService(uow_factory, FakeRenderer(), archive, clock=lambda: NOW)


def test_pdf_is_stored_and_registered(
    documents: DocumentService, archive: Path, world: World
) -> None:
    view = documents.create_pdf(
        TABLE, document_type=DocumentType.TABLE, suffix="Mai", actor_id=world.actor
    )

    path = archive / view.file_name
    assert view.file_name == f"{LOCAL_STAMP}_Buchungen_Mai.pdf"
    assert path.read_bytes() == b"%PDF-fake"
    assert view.size_bytes == path.stat().st_size
    assert view.sha256 == hashlib.sha256(b"%PDF-fake").hexdigest()
    assert view.created_by == "A A"
    assert view.document_type is DocumentType.TABLE
    assert view.exists
    assert [item.id for item in documents.list_documents()] == [view.id]


def test_creation_is_audited(
    documents: DocumentService, uow_factory: Callable[[], UnitOfWork], world: World
) -> None:
    view = documents.create_pdf(TABLE, document_type=DocumentType.REPORT, actor_id=world.actor)

    with uow_factory() as uow:
        assert uow.documents.get(view.id) is not None


def test_existing_files_are_never_overwritten(documents: DocumentService, world: World) -> None:
    first = documents.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)
    second = documents.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)

    assert first.file_name != second.file_name
    assert second.file_name.endswith("_Buchungen_2.pdf")
    assert {item.file_name for item in documents.list_documents()} == {
        first.file_name,
        second.file_name,
    }


def test_suffix_longer_than_40_characters_is_rejected(
    documents: DocumentService, archive: Path, world: World
) -> None:
    with pytest.raises(ValidationError, match="höchstens 40 Zeichen"):
        documents.create_pdf(
            TABLE, document_type=DocumentType.TABLE, suffix="x" * 41, actor_id=world.actor
        )

    assert not list(archive.glob("*.pdf")) if archive.exists() else True
    assert documents.list_documents() == []


def test_unsafe_suffix_cannot_escape_the_archive(
    documents: DocumentService, archive: Path, world: World
) -> None:
    view = documents.create_pdf(
        TABLE, document_type=DocumentType.TABLE, suffix="..\\..\\evil", actor_id=world.actor
    )

    assert (archive / view.file_name).is_file()
    assert (archive / view.file_name).parent == archive
    assert list(archive.parent.glob("*.pdf")) == []


def test_failing_renderer_leaves_no_file_and_no_entry(
    uow_factory: Callable[[], UnitOfWork], archive: Path, world: World
) -> None:
    service = DocumentService(uow_factory, FailingRenderer(), archive, clock=lambda: NOW)

    with pytest.raises(RuntimeError):
        service.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)

    assert list(archive.glob("*")) == []
    assert service.list_documents() == []


def test_verify_detects_missing_and_changed_files(documents: DocumentService, world: World) -> None:
    view = documents.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)
    path = documents.path_of(view.id)
    assert documents.verify(view.id) is DocumentState.OK

    path.write_bytes(b"%PDF-manipuliert")
    assert documents.verify(view.id) is DocumentState.CHANGED

    path.unlink()
    assert documents.verify(view.id) is DocumentState.MISSING
    assert [item.exists for item in documents.list_documents()] == [False]
    with pytest.raises(NotFoundError, match="fehlt"):
        documents.path_of(view.id)


def test_unknown_document_is_reported(documents: DocumentService) -> None:
    with pytest.raises(NotFoundError, match="nicht gefunden"):
        documents.path_of("unbekannt")


def test_newest_document_is_listed_first(
    uow_factory: Callable[[], UnitOfWork], archive: Path, world: World
) -> None:
    moments = iter([NOW, NOW.replace(minute=45)])
    service = DocumentService(uow_factory, FakeRenderer(), archive, clock=lambda: next(moments))
    old = service.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)
    new = service.create_pdf(TABLE, document_type=DocumentType.REPORT, actor_id=world.actor)

    assert [item.id for item in service.list_documents()] == [new.id, old.id]


def test_real_renderer_writes_a_valid_pdf_with_german_text(
    uow_factory: Callable[[], UnitOfWork], archive: Path, world: World
) -> None:
    service = DocumentService(uow_factory, ReportlabPdfRenderer(), archive, clock=lambda: NOW)

    view = service.create_pdf(TABLE, document_type=DocumentType.TABLE, actor_id=world.actor)

    content = (archive / view.file_name).read_bytes()
    assert content.startswith(b"%PDF-")
    assert content.rstrip().endswith(b"%%EOF")
    assert view.size_bytes > 1000
    assert service.verify(view.id) is DocumentState.OK


def test_real_renderer_handles_many_rows_and_wide_tables(
    uow_factory: Callable[[], UnitOfWork], archive: Path, world: World
) -> None:
    columns = tuple(PdfColumn(f"Spalte {index}", align_right=index % 2 == 0) for index in range(9))
    rows = tuple(
        PdfRow(tuple(f"Wert {row}/{index} " * 3 for index in range(9))) for row in range(300)
    )
    service = DocumentService(uow_factory, ReportlabPdfRenderer(), archive, clock=lambda: NOW)

    view = service.create_pdf(
        PdfTable("Breit", columns, rows), document_type=DocumentType.TABLE, actor_id=world.actor
    )

    assert (archive / view.file_name).read_bytes().count(b"/Type /Page\n") > 2
