from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, false, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.auth.api_key import ApiKeyPrincipal, authenticate_api_key, extract_api_key
from ai_gateway.catalog.repository import ModelNotFound
from ai_gateway.core.enums import ApiKeyScope, Protocol
from ai_gateway.db.models import Model, ModelRoute, Provider, ProviderProtocol
from ai_gateway.db.session import get_session
from ai_gateway.gateway.service import native_error_response

router = APIRouter(tags=["models"])

Session = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class SelectableModel:
    selectable_id: str
    canonical_name: str
    display_name: str

    @property
    def metadata(self) -> dict[str, str]:
        if self.selectable_id == self.canonical_name:
            return {}
        return {"canonical_model": self.canonical_name}


@router.get("/v1/models")
async def list_openai_models(request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.OPENAI)
        return JSONResponse(
            content={
                "object": "list",
                "data": [_openai_model(model) for model in models],
            }
        )
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.get("/v1/models/{model_id}")
async def get_openai_model(model_id: str, request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.OPENAI)
        model = next((item for item in models if item.selectable_id == model_id), None)
        if model is None:
            raise ModelNotFound(model_id)
        return JSONResponse(content=_openai_model(model))
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.get("/v1beta/models")
async def list_gemini_models(request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.GEMINI)
        return JSONResponse(content={"models": [_gemini_model(model) for model in models]})
    except Exception as exc:
        return native_error_response(Protocol.GEMINI, exc)


async def _list_selectable_models(
    session: AsyncSession,
    principal: ApiKeyPrincipal,
    protocol: Protocol,
) -> list[SelectableModel]:
    query = (
        select(Model)
        .join(ModelRoute, ModelRoute.model_id == Model.id)
        .join(Provider, Provider.id == ModelRoute.provider_id)
        .join(ProviderProtocol, ProviderProtocol.id == ModelRoute.provider_protocol_id)
        .where(
            Model.enabled.is_(True),
            ModelRoute.enabled.is_(True),
            ModelRoute.weight > 0,
            Provider.enabled.is_(True),
            ProviderProtocol.enabled.is_(True),
            ProviderProtocol.protocol == protocol,
            _scope_condition(principal),
        )
        .options(selectinload(Model.aliases))
        .distinct()
    )
    models = (await session.scalars(query)).all()
    selectable = [
        SelectableModel(
            selectable_id=model.canonical_name,
            canonical_name=model.canonical_name,
            display_name=model.display_name,
        )
        for model in models
    ]
    selectable.extend(
        SelectableModel(
            selectable_id=alias.alias,
            canonical_name=model.canonical_name,
            display_name=model.display_name,
        )
        for model in models
        for alias in model.aliases
        if alias.enabled
    )
    return sorted(selectable, key=lambda item: item.selectable_id)


def _scope_condition(principal: ApiKeyPrincipal) -> Any:
    if principal.scope is ApiKeyScope.ALL:
        return true()
    provider_allowed = (
        ModelRoute.provider_id.in_(principal.provider_ids) if principal.provider_ids else false()
    )
    model_allowed = Model.id.in_(principal.model_ids) if principal.model_ids else false()
    if principal.scope is ApiKeyScope.PROVIDERS:
        return provider_allowed
    if principal.scope is ApiKeyScope.MODELS:
        return model_allowed
    return and_(provider_allowed, model_allowed)


def _openai_model(model: SelectableModel) -> dict[str, Any]:
    return {
        "id": model.selectable_id,
        "object": "model",
        "owned_by": "gateway",
        "metadata": model.metadata,
    }


def _gemini_model(model: SelectableModel) -> dict[str, Any]:
    return {
        "name": f"models/{model.selectable_id}",
        "displayName": model.display_name,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "gatewayMetadata": model.metadata,
    }
