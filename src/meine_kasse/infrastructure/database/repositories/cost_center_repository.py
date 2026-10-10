from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from meine_kasse.domain.entities import CostCenter
from meine_kasse.domain.enums import CostCenterKind
from meine_kasse.infrastructure.database.models import CostCenterModel


def _to_entity(model: CostCenterModel) -> CostCenter:
    return CostCenter(
        id=model.id,
        name=model.name,
        number=model.number,
        valid_from=model.valid_from,
        kind=CostCenterKind(model.kind),
        notes=model.notes,
        is_active=model.is_active,
    )


class SqlCostCenterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, cost_center: CostCenter) -> None:
        self._session.add(
            CostCenterModel(
                id=cost_center.id,
                name=cost_center.name,
                number=cost_center.number,
                valid_from=cost_center.valid_from,
                kind=cost_center.kind.value,
                notes=cost_center.notes,
                is_active=cost_center.is_active,
            )
        )
        self._session.flush()

    def update(self, cost_center: CostCenter) -> None:
        model = self._session.get(CostCenterModel, cost_center.id)
        if model is None:
            raise LookupError(f"Kostenstelle {cost_center.id} existiert nicht.")
        model.name = cost_center.name
        model.number = cost_center.number
        model.valid_from = cost_center.valid_from
        model.kind = cost_center.kind.value
        model.notes = cost_center.notes
        model.is_active = cost_center.is_active
        self._session.flush()

    def get(self, cost_center_id: str) -> CostCenter | None:
        model = self._session.get(CostCenterModel, cost_center_id)
        return None if model is None else _to_entity(model)

    def get_by_number(self, number: str) -> CostCenter | None:
        statement = select(CostCenterModel).where(CostCenterModel.number == number)
        model = self._session.scalars(statement).first()
        return None if model is None else _to_entity(model)

    def list_all(self) -> Sequence[CostCenter]:
        statement = select(CostCenterModel).order_by(CostCenterModel.number)
        return [_to_entity(model) for model in self._session.scalars(statement)]
