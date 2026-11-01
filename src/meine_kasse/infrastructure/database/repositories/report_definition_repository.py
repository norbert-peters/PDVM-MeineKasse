import json
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import (
    ReportDefinition,
    ReportFilter,
    ReportGroup,
    ReportSort,
)
from meine_kasse.domain.enums import FilterOperator, ReportSource
from meine_kasse.infrastructure.database.models import ReportDefinitionModel


def _to_entity(model: ReportDefinitionModel) -> ReportDefinition:
    sort = json.loads(model.sort_json)
    return ReportDefinition(
        name=model.name,
        data_source=ReportSource(model.data_source),
        columns=tuple(json.loads(model.columns_json)),
        filters=tuple(
            ReportFilter(item["column"], FilterOperator(item["operator"]), item["value"])
            for item in json.loads(model.filters_json)
        ),
        sort=None if sort is None else ReportSort(sort["column"], sort["ascending"]),
        groups=tuple(
            ReportGroup(item["column"], item["summary_only"])
            for item in json.loads(model.grouping_json)
        ),
    )


def _write(model: ReportDefinitionModel, definition: ReportDefinition) -> None:
    model.data_source = definition.data_source.value
    model.columns_json = json.dumps(list(definition.columns), ensure_ascii=False)
    model.filters_json = json.dumps(
        [
            {"column": item.column, "operator": item.operator.value, "value": item.value}
            for item in definition.filters
        ],
        ensure_ascii=False,
    )
    model.sort_json = json.dumps(
        None
        if definition.sort is None
        else {"column": definition.sort.column, "ascending": definition.sort.ascending}
    )
    model.grouping_json = json.dumps(
        [{"column": item.column, "summary_only": item.summary_only} for item in definition.groups]
    )


class SqlReportDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: str, name: str) -> ReportDefinition | None:
        model = self._find(user_id, name)
        return None if model is None else _to_entity(model)

    def list_for_user(self, user_id: str) -> Sequence[ReportDefinition]:
        statement = (
            select(ReportDefinitionModel)
            .where(ReportDefinitionModel.user_id == user_id)
            .order_by(func.lower(ReportDefinitionModel.name))
        )
        return [_to_entity(model) for model in self._session.scalars(statement)]

    def save(self, user_id: str, definition: ReportDefinition) -> None:
        model = self._find(user_id, definition.name)
        if model is None:
            model = ReportDefinitionModel(user_id=user_id, name=definition.name)
            self._session.add(model)
        _write(model, definition)
        self._session.flush()

    def delete(self, user_id: str, name: str) -> None:
        self._session.execute(
            delete(ReportDefinitionModel).where(
                ReportDefinitionModel.user_id == user_id, ReportDefinitionModel.name == name
            )
        )
        self._session.flush()

    def _find(self, user_id: str, name: str) -> ReportDefinitionModel | None:
        statement = select(ReportDefinitionModel).where(
            ReportDefinitionModel.user_id == user_id, ReportDefinitionModel.name == name
        )
        return self._session.scalars(statement).first()
