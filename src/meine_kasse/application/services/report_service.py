"""Auswertungen: Ausführen, PDF-Ausgabe und gespeicherte Definitionen (Vorgabe 2.14)."""

import json
from collections.abc import Sequence

from meine_kasse.application.ports import UnitOfWorkFactory
from meine_kasse.application.reporting.catalog import SOURCES, SourceDef
from meine_kasse.application.reporting.engine import ReportResult, run_report, validate_definition
from meine_kasse.application.reporting.sources import (
    Row,
    account_rows,
    booking_rows,
    plan_actual_rows,
    plan_targets,
)
from meine_kasse.application.services.document_service import DocumentService, DocumentView
from meine_kasse.application.services.planning_service import PlanningService
from meine_kasse.domain.entities import AuditEntry, ReportDefinition
from meine_kasse.domain.enums import DocumentType, ReportSource
from meine_kasse.domain.errors import NotFoundError, ValidationError

_MAX_NAME_LENGTH = 200


class ReportService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        planning: PlanningService,
        documents: DocumentService,
    ) -> None:
        self._uow_factory = uow_factory
        self._planning = planning
        self._documents = documents

    @staticmethod
    def sources() -> Sequence[SourceDef]:
        return list(SOURCES.values())

    def run(self, definition: ReportDefinition) -> ReportResult:
        validate_definition(definition)
        return run_report(definition, self._rows(definition.data_source))

    def export_pdf(
        self, definition: ReportDefinition, *, suffix: str = "", actor_id: str
    ) -> DocumentView:
        """Führt die Auswertung aus und legt das PDF im Dokumentenarchiv ab."""
        result = self.run(definition)
        return self._documents.create_pdf(
            result.to_pdf_table(),
            document_type=DocumentType.REPORT,
            suffix=suffix,
            actor_id=actor_id,
        )

    # Gespeicherte Auswertungen

    def list_definitions(self, user_id: str) -> Sequence[ReportDefinition]:
        with self._uow_factory() as uow:
            return uow.report_definitions.list_for_user(user_id)

    def save_definition(self, user_id: str, definition: ReportDefinition) -> None:
        """Speichert unter dem Namen; eine gleichnamige Auswertung des Anwenders wird ersetzt."""
        name = definition.name.strip()
        if not name:
            raise ValidationError("Bitte einen Namen für die Auswertung eingeben.")
        if len(name) > _MAX_NAME_LENGTH:
            raise ValidationError(f"Der Name darf höchstens {_MAX_NAME_LENGTH} Zeichen lang sein.")
        definition = ReportDefinition(
            name=name,
            data_source=definition.data_source,
            columns=definition.columns,
            filters=definition.filters,
            sort=definition.sort,
            groups=definition.groups,
        )
        validate_definition(definition)
        with self._uow_factory() as uow:
            existed = uow.report_definitions.get(user_id, name) is not None
            uow.report_definitions.save(user_id, definition)
            uow.audit.add(
                AuditEntry(
                    name="report_definition.update" if existed else "report_definition.create",
                    entity="report_definitions",
                    entity_id=None,
                    user_id=user_id,
                    new_value=json.dumps(
                        {"name": name, "data_source": definition.data_source.value},
                        ensure_ascii=False,
                    ),
                )
            )
            uow.commit()

    def delete_definition(self, user_id: str, name: str) -> None:
        with self._uow_factory() as uow:
            if uow.report_definitions.get(user_id, name) is None:
                raise NotFoundError("Die gespeicherte Auswertung wurde nicht gefunden.")
            uow.report_definitions.delete(user_id, name)
            uow.audit.add(
                AuditEntry(
                    name="report_definition.delete",
                    entity="report_definitions",
                    entity_id=None,
                    user_id=user_id,
                    old_value=json.dumps({"name": name}, ensure_ascii=False),
                )
            )
            uow.commit()

    # Intern

    def _rows(self, source: ReportSource) -> Sequence[Row]:
        if source is ReportSource.PLAN_ACTUAL:
            with self._uow_factory() as uow:
                targets = plan_targets(uow)
            # Die Planansichten öffnen eigene Transaktionen und folgen deshalb nach der ersten.
            views = [
                (cost_center, self._planning.get_plan_view(cost_center.id, year))
                for cost_center, year in targets
            ]
            return plan_actual_rows(views)
        with self._uow_factory() as uow:
            return booking_rows(uow) if source is ReportSource.BOOKINGS else account_rows(uow)
