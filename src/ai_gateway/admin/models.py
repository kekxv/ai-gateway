from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_gateway.admin.audit import log_multiplier_change
from ai_gateway.auth.dependencies import admin_user, current_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.catalog.schemas import (
    ModelAliasInput,
    ModelAliasResponse,
    ModelCreate,
    ModelPriceTierInput,
    ModelPriceTierResponse,
    ModelResponse,
    ModelRouteCreate,
    ModelRouteResponse,
    ModelRouteUpdate,
    ModelUpdate,
    PublicModelPriceTierResponse,
    RoutingStrategy,
    UserModelResponse,
    alias_values,
)
from ai_gateway.core.enums import RouteRuntimeState, RouteSource
from ai_gateway.db.models import (
    ApiKeyModel,
    Model,
    ModelAlias,
    ModelPriceTier,
    ModelRoute,
    Provider,
    ProviderProtocol,
    RequestLog,
    User,
)
from ai_gateway.db.session import get_session

models_router = APIRouter(prefix="/admin/models", tags=["admin-models"])
routes_router = APIRouter(prefix="/admin/model-routes", tags=["admin-model-routes"])
user_models_router = APIRouter(prefix="/user/models", tags=["user-models"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
CurrentUser = Annotated[User, Depends(current_user)]


@models_router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(payload: ModelCreate, session: Session, _: AdminUser) -> ModelResponse:
    aliases = alias_values(payload.aliases)
    await _validate_catalog_names(
        session,
        model_id=None,
        canonical_name=payload.canonical_name,
    )
    model = Model(
        canonical_name=payload.canonical_name,
        display_name=payload.display_name,
        input_price_per_million=payload.input_price_per_million,
        output_price_per_million=payload.output_price_per_million,
        cache_read_price_per_million=payload.cache_read_price_per_million,
        cache_write_price_per_million=payload.cache_write_price_per_million,
        enabled=payload.enabled,
        routing_strategy=payload.routing_strategy,
        price_multiplier=payload.price_multiplier,
        aliases=[ModelAlias(alias=item.alias, enabled=item.enabled) for item in aliases],
        price_tiers=[_new_price_tier(item) for item in payload.price_tiers],
    )
    if payload.price_tiers:
        _sync_legacy_prices(model, payload.price_tiers[0])
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
        await session.scalars(
            select(Model)
            .options(selectinload(Model.aliases), selectinload(Model.price_tiers))
            .order_by(Model.id)
        )
    ).all()
    return [_model_response(model) for model in models]


@user_models_router.get("", response_model=list[UserModelResponse])
async def list_available_models(session: Session, _: CurrentUser) -> list[UserModelResponse]:
    models = (
        await session.scalars(
            select(Model)
            .where(Model.enabled.is_(True))
            .options(selectinload(Model.aliases), selectinload(Model.price_tiers))
            .order_by(Model.id)
        )
    ).all()
    multiplier_rows = (
        await session.execute(
            select(ModelRoute.model_id, Provider.public_multiplier)
            .join(Provider, Provider.id == ModelRoute.provider_id)
            .join(ProviderProtocol, ProviderProtocol.provider_id == Provider.id)
            .where(
                ModelRoute.enabled.is_(True),
                ModelRoute.weight > 0,
                Provider.enabled.is_(True),
                ProviderProtocol.enabled.is_(True),
            )
            .distinct()
        )
    ).all()
    public_multipliers: dict[int, list[Decimal]] = {}
    for model_id, multiplier in multiplier_rows:
        public_multipliers.setdefault(model_id, []).append(multiplier)
    return [
        _user_model_response(
            model,
            provider_multipliers=public_multipliers.get(model.id, []),
        )
        for model in models
    ]


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
    if payload.cache_read_price_per_million is not None:
        model.cache_read_price_per_million = payload.cache_read_price_per_million
    if payload.cache_write_price_per_million is not None:
        model.cache_write_price_per_million = payload.cache_write_price_per_million
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
    if payload.price_tiers is not None:
        model.price_tiers = [_new_price_tier(item) for item in payload.price_tiers]
        if payload.price_tiers:
            _sync_legacy_prices(model, payload.price_tiers[0])
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
    )
    route = ModelRoute(
        model_id=payload.model_id,
        provider_id=payload.provider_id,
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


@routes_router.post("/{route_id}/recover", response_model=ModelRouteResponse)
async def recover_model_route(
    route_id: int,
    session: Session,
    _: AdminUser,
) -> ModelRouteResponse:
    route = await _get_route(session, route_id)
    route.runtime_state = RouteRuntimeState.CLOSED
    route.consecutive_failures = 0
    route.disabled_until = None
    route.last_error_code = None
    route.last_error_at = None
    await session.flush()
    response = _route_response(route)
    await session.commit()
    return response


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
    upstream_model = payload.upstream_model or route.upstream_model
    await _validate_route_relations(
        session,
        model_id=model_id,
        provider_id=provider_id,
    )
    route.model_id = model_id
    route.provider_id = provider_id
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
    await session.execute(
        update(RequestLog).where(RequestLog.model_route_id == route_id).values(model_route_id=None)
    )
    await session.execute(delete(ModelRoute).where(ModelRoute.id == route_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_model(session: AsyncSession, model_id: int) -> Model:
    model = await session.scalar(
        select(Model)
        .where(Model.id == model_id)
        .options(selectinload(Model.aliases), selectinload(Model.price_tiers))
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
) -> None:
    model_query = select(Model.id).where(Model.canonical_name == canonical_name)
    if model_id is not None:
        model_query = model_query.where(Model.id != model_id)
    if await session.scalar(model_query.limit(1)) is not None:
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "model_name_conflict",
            "Canonical model names must be unique",
        )


async def _validate_route_relations(
    session: AsyncSession,
    *,
    model_id: int,
    provider_id: int,
) -> None:
    model = await session.get(Model, model_id)
    provider = await session.get(Provider, provider_id)
    protocol_id = await session.scalar(
        select(ProviderProtocol.id).where(ProviderProtocol.provider_id == provider_id).limit(1)
    )
    if model is None or provider is None or protocol_id is None:
        raise_auth_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_route_reference",
            "Model and provider with at least one protocol must exist",
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


def _model_response(model: Model, *, enabled_aliases_only: bool = False) -> ModelResponse:
    aliases = sorted(
        (alias for alias in model.aliases if alias.enabled or not enabled_aliases_only),
        key=lambda item: item.id,
    )
    return ModelResponse(
        id=model.id,
        canonical_name=model.canonical_name,
        display_name=model.display_name,
        input_price_per_million=model.input_price_per_million,
        output_price_per_million=model.output_price_per_million,
        cache_read_price_per_million=model.cache_read_price_per_million,
        cache_write_price_per_million=model.cache_write_price_per_million,
        enabled=model.enabled,
        aliases=[
            ModelAliasResponse(id=alias.id, alias=alias.alias, enabled=alias.enabled)
            for alias in aliases
        ],
        routing_strategy=cast(RoutingStrategy, model.routing_strategy),
        created_at=model.created_at,
        updated_at=model.updated_at,
        price_multiplier=model.price_multiplier,
        price_tiers=[
            ModelPriceTierResponse(
                id=tier.id,
                max_input_tokens=tier.max_input_tokens,
                input_price_per_million=tier.input_price_per_million,
                output_price_per_million=tier.output_price_per_million,
                cache_read_price_per_million=tier.cache_read_price_per_million,
                cache_write_price_per_million=tier.cache_write_price_per_million,
            )
            for tier in _ordered_price_tiers(model.price_tiers)
        ],
    )


def _user_model_response(
    model: Model,
    *,
    provider_multipliers: list[Decimal],
) -> UserModelResponse:
    aliases = sorted((alias for alias in model.aliases if alias.enabled), key=lambda item: item.id)
    configured_tiers: list[Model | ModelPriceTier] = (
        list(_ordered_price_tiers(model.price_tiers)) if model.price_tiers else [model]
    )
    public_tiers: list[PublicModelPriceTierResponse] = []
    for tier in configured_tiers:
        if not provider_multipliers:
            break
        factor_values = [model.price_multiplier * value for value in provider_multipliers]

        def price_range(value: Decimal) -> tuple[Decimal, Decimal]:
            values = [
                (value * factor).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                for factor in factor_values
            ]
            return min(values), max(values)

        input_min, input_max = price_range(tier.input_price_per_million)
        output_min, output_max = price_range(tier.output_price_per_million)
        cache_read_min, cache_read_max = price_range(tier.cache_read_price_per_million)
        cache_write_min, cache_write_max = price_range(tier.cache_write_price_per_million)
        public_tiers.append(
            PublicModelPriceTierResponse(
                max_input_tokens=getattr(tier, "max_input_tokens", None),
                input_price_per_million_min=input_min,
                input_price_per_million_max=input_max,
                output_price_per_million_min=output_min,
                output_price_per_million_max=output_max,
                cache_read_price_per_million_min=cache_read_min,
                cache_read_price_per_million_max=cache_read_max,
                cache_write_price_per_million_min=cache_write_min,
                cache_write_price_per_million_max=cache_write_max,
            )
        )
    return UserModelResponse(
        id=model.id,
        canonical_name=model.canonical_name,
        display_name=model.display_name,
        input_price_per_million=(
            public_tiers[0].input_price_per_million_min if public_tiers else Decimal("0")
        ),
        output_price_per_million=(
            public_tiers[0].output_price_per_million_min if public_tiers else Decimal("0")
        ),
        cache_read_price_per_million=(
            public_tiers[0].cache_read_price_per_million_min if public_tiers else Decimal("0")
        ),
        cache_write_price_per_million=(
            public_tiers[0].cache_write_price_per_million_min if public_tiers else Decimal("0")
        ),
        price_multiplier=Decimal("1"),
        enabled=model.enabled,
        aliases=[
            ModelAliasResponse(id=alias.id, alias=alias.alias, enabled=alias.enabled)
            for alias in aliases
        ],
        routing_strategy=cast(RoutingStrategy, model.routing_strategy),
        created_at=model.created_at,
        updated_at=model.updated_at,
        public_price_tiers=public_tiers,
    )


def _new_price_tier(payload: ModelPriceTierInput) -> ModelPriceTier:
    return ModelPriceTier(
        max_input_tokens=payload.max_input_tokens,
        input_price_per_million=payload.input_price_per_million,
        output_price_per_million=payload.output_price_per_million,
        cache_read_price_per_million=payload.cache_read_price_per_million,
        cache_write_price_per_million=payload.cache_write_price_per_million,
    )


def _sync_legacy_prices(model: Model, tier: ModelPriceTierInput) -> None:
    model.input_price_per_million = tier.input_price_per_million
    model.output_price_per_million = tier.output_price_per_million
    model.cache_read_price_per_million = tier.cache_read_price_per_million
    model.cache_write_price_per_million = tier.cache_write_price_per_million


def _ordered_price_tiers(tiers: list[ModelPriceTier]) -> list[ModelPriceTier]:
    return sorted(
        tiers,
        key=lambda tier: (
            tier.max_input_tokens is None,
            tier.max_input_tokens or 0,
        ),
    )


def _route_response(route: ModelRoute) -> ModelRouteResponse:
    return ModelRouteResponse(
        id=route.id,
        model_id=route.model_id,
        provider_id=route.provider_id,
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
        "Canonical model names must be unique; aliases must be unique within each model",
    )


def _raise_route_conflict() -> NoReturn:
    raise_auth_error(
        status.HTTP_409_CONFLICT,
        "model_route_conflict",
        "A route already exists for this model and provider",
    )
