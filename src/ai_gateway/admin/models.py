from __future__ import annotations

from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.admin.audit import log_multiplier_change
from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.schemas import (
    ModelAliasInput,
    ModelAliasResponse,
    ModelCreate,
    ModelResponse,
    ModelRouteCreate,
    ModelRouteResponse,
    ModelRouteUpdate,
    ModelUpdate,
    RoutingStrategy,
    alias_values,
)
from ai_gateway.core.enums import RouteSource
from ai_gateway.db.models import (
    ApiKeyModel,
    Model,
    ModelAlias,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.db.session import get_session

models_router = APIRouter(prefix="/admin/models", tags=["admin-models"])
routes_router = APIRouter(prefix="/admin/model-routes", tags=["admin-model-routes"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]


@models_router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(payload: ModelCreate, session: Session, _: AdminUser) -> ModelResponse:
    aliases = alias_values(payload.aliases)
    await _validate_catalog_names(
        session,
        model_id=None,
        canonical_name=payload.canonical_name,
        aliases=aliases,
    )
    model = Model(
        canonical_name=payload.canonical_name,
        display_name=payload.display_name,
        input_price_per_million=payload.input_price_per_million,
        output_price_per_million=payload.output_price_per_million,
        enabled=payload.enabled,
        routing_strategy=payload.routing_strategy,
        price_multiplier=payload.price_multiplier,
        aliases=[ModelAlias(alias=item.alias, enabled=item.enabled) for item in aliases],
    )
    session.add(model)
    try:
        await session.flush()
        await session.refresh(model, attribute_names=["created_at", "updated_at"])
        response = _model_response(model)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_model_conflict()
    return response


@models_router.get("", response_model=list[ModelResponse])
async def list_models(session: Session, _: AdminUser) -> list[ModelResponse]:
    models = (
        await session.scalars(select(Model).options(selectinload(Model.aliases)).order_by(Model.id))
    ).all()
    return [_model_response(model) for model in models]


@models_router.get("/{model_id}", response_model=ModelResponse)
async def get_model(model_id: int, session: Session, _: AdminUser) -> ModelResponse:
    return _model_response(await _get_model(session, model_id))


@models_router.patch("/{model_id}", response_model=ModelResponse)
@models_router.put("/{model_id}", response_model=ModelResponse, include_in_schema=False)
async def update_model(
    model_id: int,
    payload: ModelUpdate,
    session: Session,
    admin: AdminUser,
) -> ModelResponse:
    model = await _get_model(session, model_id)
    aliases = alias_values(payload.aliases) if payload.aliases is not None else None
    await _validate_catalog_names(
        session,
        model_id=model.id,
        canonical_name=payload.canonical_name or model.canonical_name,
        aliases=(
            aliases
            if aliases is not None
            else [ModelAliasInput(alias=item.alias, enabled=item.enabled) for item in model.aliases]
        ),
    )
    old_multiplier = model.price_multiplier
    if payload.canonical_name is not None:
        model.canonical_name = payload.canonical_name
    if payload.display_name is not None:
        model.display_name = payload.display_name
    if payload.input_price_per_million is not None:
        model.input_price_per_million = payload.input_price_per_million
    if payload.output_price_per_million is not None:
        model.output_price_per_million = payload.output_price_per_million
    if payload.enabled is not None:
        model.enabled = payload.enabled
    if payload.routing_strategy is not None:
        model.routing_strategy = payload.routing_strategy
    if payload.price_multiplier is not None:
        model.price_multiplier = payload.price_multiplier
        await log_multiplier_change(
            session=session,
            user_id=admin.id,
            resource_type="model",
            resource_id=model_id,
            old_value=old_multiplier,
            new_value=payload.price_multiplier,
        )
    if aliases is not None:
        _replace_aliases(model, aliases)
    try:
        await session.flush()
        await session.refresh(model, attribute_names=["updated_at"])
        response = _model_response(model)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_model_conflict()
    return response


@models_router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: int, session: Session, _: AdminUser) -> Response:
    await _get_model(session, model_id)
    route_ids = list(
        await session.scalars(select(ModelRoute.id).where(ModelRoute.model_id == model_id))
    )
    history_filter = RequestLog.model_id == model_id
    if route_ids:
        history_filter = or_(history_filter, RequestLog.model_route_id.in_(route_ids))
    history_id = await session.scalar(select(RequestLog.id).where(history_filter).limit(1))
    if history_id is not None:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "model_has_history",
            "Models with request history must be disabled instead of deleted",
        )
    await session.execute(delete(ApiKeyModel).where(ApiKeyModel.model_id == model_id))
    await session.execute(delete(ModelRoute).where(ModelRoute.model_id == model_id))
    await session.execute(delete(ModelAlias).where(ModelAlias.model_id == model_id))
    await session.execute(delete(Model).where(Model.id == model_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@routes_router.post("", response_model=ModelRouteResponse, status_code=status.HTTP_201_CREATED)
async def create_model_route(
    payload: ModelRouteCreate,
    session: Session,
    _: AdminUser,
) -> ModelRouteResponse:
    await _validate_route_relations(
        session,
        model_id=payload.model_id,
        provider_id=payload.provider_id,
        provider_protocol_id=payload.provider_protocol_id,
    )
    route = ModelRoute(
        model_id=payload.model_id,
        provider_id=payload.provider_id,
        provider_protocol_id=payload.provider_protocol_id,
        upstream_model=payload.upstream_model,
        weight=payload.weight,
        enabled=payload.enabled,
        source=RouteSource.MANUAL,
    )
    session.add(route)
    try:
        await session.flush()
        response = _route_response(route)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_route_conflict()
    return response


@routes_router.get("", response_model=list[ModelRouteResponse])
async def list_model_routes(
    session: Session,
    _: AdminUser,
    model_id: int | None = None,
    provider_id: int | None = None,
) -> list[ModelRouteResponse]:
    query = select(ModelRoute).order_by(ModelRoute.id)
    if model_id is not None:
        query = query.where(ModelRoute.model_id == model_id)
    if provider_id is not None:
        query = query.where(ModelRoute.provider_id == provider_id)
    routes = (await session.scalars(query)).all()
    return [_route_response(route) for route in routes]


@routes_router.get("/{route_id}", response_model=ModelRouteResponse)
async def get_model_route(route_id: int, session: Session, _: AdminUser) -> ModelRouteResponse:
    return _route_response(await _get_route(session, route_id))


@routes_router.patch("/{route_id}", response_model=ModelRouteResponse)
@routes_router.put("/{route_id}", response_model=ModelRouteResponse, include_in_schema=False)
async def update_model_route(
    route_id: int,
    payload: ModelRouteUpdate,
    session: Session,
    _: AdminUser,
) -> ModelRouteResponse:
    route = await _get_route(session, route_id)
    model_id = payload.model_id if payload.model_id is not None else route.model_id
    provider_id = payload.provider_id if payload.provider_id is not None else route.provider_id
    provider_protocol_id = (
        payload.provider_protocol_id
        if payload.provider_protocol_id is not None
        else route.provider_protocol_id
    )
    upstream_model = payload.upstream_model or route.upstream_model
    await _validate_route_relations(
        session,
        model_id=model_id,
        provider_id=provider_id,
        provider_protocol_id=provider_protocol_id,
    )
    route.model_id = model_id
    route.provider_id = provider_id
    route.provider_protocol_id = provider_protocol_id
    route.upstream_model = upstream_model
    if payload.weight is not None:
        route.weight = payload.weight
    if payload.enabled is not None:
        route.enabled = payload.enabled
    try:
        await session.flush()
        response = _route_response(route)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        _raise_route_conflict()
    return response


@routes_router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_route(route_id: int, session: Session, _: AdminUser) -> Response:
    await _get_route(session, route_id)
    history_id = await session.scalar(
        select(RequestLog.id).where(RequestLog.model_route_id == route_id).limit(1)
    )
    if history_id is not None:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "model_route_has_history",
            "Routes with request history must be disabled instead of deleted",
        )
    await session.execute(delete(ModelRoute).where(ModelRoute.id == route_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_model(session: AsyncSession, model_id: int) -> Model:
    model = await session.scalar(
        select(Model).where(Model.id == model_id).options(selectinload(Model.aliases))
    )
    if model is None:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "model_not_found", "Model not found")
    return model


async def _get_route(session: AsyncSession, route_id: int) -> ModelRoute:
    route = await session.get(ModelRoute, route_id)
    if route is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "model_route_not_found",
            "Model route not found",
        )
    return route


async def _validate_catalog_names(
    session: AsyncSession,
    *,
    model_id: int | None,
    canonical_name: str,
    aliases: list[ModelAliasInput],
) -> None:
    alias_names = {item.alias for item in aliases}
    if canonical_name in alias_names:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ambiguous_model_name",
            "A canonical model name cannot also be an alias",
        )
    model_query = select(Model.id).where(
        or_(Model.canonical_name == canonical_name, Model.canonical_name.in_(alias_names))
    )
    alias_query = select(ModelAlias.model_id).where(
        or_(ModelAlias.alias == canonical_name, ModelAlias.alias.in_(alias_names))
    )
    if model_id is not None:
        model_query = model_query.where(Model.id != model_id)
        alias_query = alias_query.where(ModelAlias.model_id != model_id)
    if (
        await session.scalar(model_query.limit(1)) is not None
        or await session.scalar(alias_query.limit(1)) is not None
    ):
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "model_name_conflict",
            "Canonical model names and aliases must be unique",
        )


async def _validate_route_relations(
    session: AsyncSession,
    *,
    model_id: int,
    provider_id: int,
    provider_protocol_id: int,
) -> None:
    model = await session.get(Model, model_id)
    provider = await session.get(Provider, provider_id)
    protocol = await session.get(ProviderProtocol, provider_protocol_id)
    if model is None or provider is None or protocol is None:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_route_reference",
            "Model, provider, and provider protocol must exist",
        )
    if protocol.provider_id != provider_id:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "provider_protocol_mismatch",
            "Provider protocol must belong to the selected provider",
        )


def _replace_aliases(model: Model, aliases: list[ModelAliasInput]) -> None:
    existing = {item.alias: item for item in model.aliases}
    replacements: list[ModelAlias] = []
    for payload in aliases:
        alias = existing.get(payload.alias)
        if alias is None:
            alias = ModelAlias(alias=payload.alias)
        alias.enabled = payload.enabled
        replacements.append(alias)
    model.aliases = replacements


def _model_response(model: Model) -> ModelResponse:
    aliases = sorted(model.aliases, key=lambda item: item.id)
    return ModelResponse(
        id=model.id,
        canonical_name=model.canonical_name,
        display_name=model.display_name,
        input_price_per_million=model.input_price_per_million,
        output_price_per_million=model.output_price_per_million,
        enabled=model.enabled,
        aliases=[
            ModelAliasResponse(id=alias.id, alias=alias.alias, enabled=alias.enabled)
            for alias in aliases
        ],
        routing_strategy=cast(RoutingStrategy, model.routing_strategy),
        created_at=model.created_at,
        updated_at=model.updated_at,
        price_multiplier=model.price_multiplier,
    )


def _route_response(route: ModelRoute) -> ModelRouteResponse:
    return ModelRouteResponse(
        id=route.id,
        model_id=route.model_id,
        provider_id=route.provider_id,
        provider_protocol_id=route.provider_protocol_id,
        upstream_model=route.upstream_model,
        weight=route.weight,
        enabled=route.enabled,
        source=route.source,
        runtime_state=route.runtime_state,
        consecutive_failures=route.consecutive_failures,
        disabled_until=route.disabled_until,
        last_error_code=route.last_error_code,
        last_error_at=route.last_error_at,
    )


def _raise_model_conflict() -> NoReturn:
    raise_auth_error(
        status.HTTP_409_CONFLICT,
        "model_conflict",
        "Canonical model names and aliases must be unique",
    )


def _raise_route_conflict() -> NoReturn:
    raise_auth_error(
        status.HTTP_409_CONFLICT,
        "model_route_conflict",
        "A route already exists for this model, provider, and provider protocol",
    )
