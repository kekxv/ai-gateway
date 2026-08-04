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
        if model is not None:
            return ResolvedModel(
                model_id=model.id,
                requested_name=name,
                canonical_name=model.canonical_name,
            )

        models = (
            await self._session.scalars(
                select(Model)
                .join(ModelAlias)
                .where(
                    ModelAlias.alias == name,
                    ModelAlias.enabled.is_(True),
                    Model.enabled.is_(True),
                )
                .distinct()
                .order_by(Model.id)
            )
        ).all()
        if not models:
            raise ModelNotFound(name)
        return ResolvedModel(
            model_id=models[0].id,
            requested_name=name,
            canonical_name=models[0].canonical_name if len(models) == 1 else None,
            model_ids=tuple(model.id for model in models),
        )


Catalog = CatalogRepository
