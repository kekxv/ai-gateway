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
    canonical_name: str | None
    display_name: str

    @property
    def metadata(self) -> dict[str, str]:
        if self.canonical_name is None or self.selectable_id == self.canonical_name:
            return {}
        return {"canonical_model": self.canonical_name}


@router.get("/v1/models")
async def list_models(request: Request, session: Session) -> Response:
    """List models - dispatches to OpenAI or Claude format based on request headers."""
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)

        # Check if this is a Claude-style request (has anthropic-version header)
        is_claude_request = bool(request.headers.get("anthropic-version"))

        if is_claude_request:
            models = await _list_selectable_models(session, principal, Protocol.CLAUDE)
            return JSONResponse(
                content={
                    "data": [_claude_model(model) for model in models],
                }
            )
        else:
            # Default to OpenAI format
            models = await _list_selectable_models(session, principal, Protocol.OPENAI)
            return JSONResponse(
                content={
                    "object": "list",
                    "data": [_openai_model(model) for model in models],
                }
            )
    except Exception as exc:
        # Determine which error format to use
        is_claude_request = bool(request.headers.get("anthropic-version"))
        protocol = Protocol.CLAUDE if is_claude_request else Protocol.OPENAI
        return native_error_response(protocol, exc)


@router.get("/anthropic/v1/models")
async def list_anthropic_models(request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.CLAUDE)
        return JSONResponse(content={"data": [_claude_model(model) for model in models]})
    except Exception as exc:
        return native_error_response(Protocol.CLAUDE, exc)


@router.get("/anthropic/v1/models/{model_id:path}")
async def get_anthropic_model(model_id: str, request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.CLAUDE)
        requested_key = _selector_key(model_id)
        model = next(
            (item for item in models if _selector_key(item.selectable_id) == requested_key),
            None,
        )
        if model is None:
            raise ModelNotFound(model_id)
        return JSONResponse(content=_claude_model(model))
    except Exception as exc:
        return native_error_response(Protocol.CLAUDE, exc)


@router.get("/v1/models/{model_id:path}")
async def get_openai_model(model_id: str, request: Request, session: Session) -> Response:
    try:
        principal = await authenticate_api_key(extract_api_key(request), session)
        models = await _list_selectable_models(session, principal, Protocol.OPENAI)
        requested_key = _selector_key(model_id)
        model = next(
            (item for item in models if _selector_key(item.selectable_id) == requested_key),
            None,
        )
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
        .join(ProviderProtocol, ProviderProtocol.provider_id == ModelRoute.provider_id)
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
        .order_by(Model.id)
    )
    models = (await session.scalars(query)).all()
    targets_by_key: dict[str, tuple[str, dict[int, Model]]] = {}
    for model in models:
        names = [model.canonical_name]
        names.extend(alias.alias for alias in model.aliases if alias.enabled)
        for name in names:
            key = _selector_key(name)
            selector = targets_by_key.get(key)
            if selector is None:
                targets_by_key[key] = (name, {model.id: model})
            else:
                selector[1][model.id] = model

    selectable: list[SelectableModel] = []
    for name, targets_by_id in targets_by_key.values():
        targets = list(targets_by_id.values())
        if len(targets) == 1:
            target = targets[0]
            canonical_name = target.canonical_name
            display_name = target.display_name
        else:
            canonical_name = None
            display_name = name
        selectable.append(
            SelectableModel(
                selectable_id=name,
                canonical_name=canonical_name,
                display_name=display_name,
            )
        )
    return sorted(selectable, key=lambda item: item.selectable_id)


def _selector_key(name: str) -> str:
    return name.casefold()


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


def _claude_model(model: SelectableModel) -> dict[str, Any]:
    return {
        "id": model.selectable_id,
        "display_name": model.display_name,
        # Placeholder; gateway doesn't track creation time per model.
        "created_at": "2024-01-01T00:00:00Z",
    }
