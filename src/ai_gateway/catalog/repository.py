from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.core.errors import GatewayError
from ai_gateway.db.models import Model, ModelAlias

from .schemas import ResolvedModel


class ModelNotFound(GatewayError):
    code = "model_not_found"
    status_code = 404

    def __init__(self, requested_name: str) -> None:
        self.requested_name = requested_name
        super().__init__(f"Model {requested_name!r} was not found")


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_model(self, name: str) -> ResolvedModel:
        model = await self._session.scalar(
            select(Model).where(Model.canonical_name == name, Model.enabled.is_(True))
        )
        if model is None:
            model = await self._session.scalar(
                select(Model)
                .join(ModelAlias)
                .where(
                    ModelAlias.alias == name,
                    ModelAlias.enabled.is_(True),
                    Model.enabled.is_(True),
                )
            )
        if model is None:
            raise ModelNotFound(name)
        return ResolvedModel(
            model_id=model.id,
            requested_name=name,
            canonical_name=model.canonical_name,
        )


Catalog = CatalogRepository
