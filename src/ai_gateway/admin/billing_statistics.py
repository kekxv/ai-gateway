from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import admin_user, current_user
from ai_gateway.core.enums import RequestStatus
from ai_gateway.db.models import ApiKey, Model, Provider, RequestLog, User
from ai_gateway.db.session import get_session

admin_router = APIRouter(prefix="/admin/billing-statistics", tags=["admin-billing-statistics"])
user_router = APIRouter(prefix="/user/billing-statistics", tags=["user-billing-statistics"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
CurrentUser = Annotated[User, Depends(current_user)]

_MAX_FILTER_VALUES = 200
_MAX_RANGE = timedelta(days=366)


class UserBillingTotals(BaseModel):
    requests: int
    failed_requests: int
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    user_cost: Decimal
    average_latency_ms: int | None


class AdminBillingTotals(UserBillingTotals):
    cost_amount: Decimal
    gross_profit: Decimal


class UserBillingDailyPoint(UserBillingTotals):
    date: date


class AdminBillingDailyPoint(AdminBillingTotals):
    date: date


class UserBillingDimensionStat(UserBillingTotals):
    id: int | None
    name: str


class AdminBillingDimensionStat(AdminBillingTotals):
    id: int | None
    name: str


class UserBillingStatisticsResponse(BaseModel):
    totals: UserBillingTotals
    daily_usage: list[UserBillingDailyPoint]
    model_stats: list[UserBillingDimensionStat]
    api_key_stats: list[UserBillingDimensionStat]


class AdminBillingStatisticsResponse(BaseModel):
    totals: AdminBillingTotals
    daily_usage: list[AdminBillingDailyPoint]
    provider_stats: list[AdminBillingDimensionStat]
    model_stats: list[AdminBillingDimensionStat]
    api_key_stats: list[AdminBillingDimensionStat]


def _validation_error(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def _database_datetime(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise _validation_error("timestamps must include a timezone")
    return value.astimezone(UTC).replace(tzinfo=None)


def _normalise_ids(values: list[int] | None) -> list[int]:
    deduplicated = list(dict.fromkeys(values or []))
    if len(deduplicated) > _MAX_FILTER_VALUES:
        raise _validation_error(f"at most {_MAX_FILTER_VALUES} filter values are allowed")
    return deduplicated


def _normalise_range(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    start = _database_datetime(start_at)
    end = _database_datetime(end_at)
    if end < start:
        raise _validation_error("end_at must not be earlier than start_at")
    if end - start > _MAX_RANGE:
        raise _validation_error("time range must not exceed 366 days")
    return start, end


def _filters(
    *,
    start_at: datetime,
    end_at: datetime,
    owner_user_id: int | None,
    provider_ids: list[int],
    model_ids: list[int],
    api_key_ids: list[int],
) -> list[Any]:
    conditions: list[Any] = [
        RequestLog.created_at >= start_at,
        RequestLog.created_at <= end_at,
    ]
    if owner_user_id is not None:
        conditions.append(RequestLog.user_id == owner_user_id)
    if provider_ids:
        conditions.append(RequestLog.provider_id.in_(provider_ids))
    if model_ids:
        conditions.append(RequestLog.model_id.in_(model_ids))
    if api_key_ids:
        conditions.append(RequestLog.api_key_id.in_(api_key_ids))
    return conditions


def _aggregate_columns() -> tuple[Any, ...]:
    return (
        func.count(RequestLog.id).label("requests"),
        func.coalesce(
            func.sum(case((RequestLog.status == RequestStatus.FAILED, 1), else_=0)),
            0,
        ).label("failed_requests"),
        func.coalesce(func.sum(RequestLog.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(RequestLog.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(RequestLog.cache_read_tokens), 0).label("cache_read_tokens"),
        func.coalesce(func.sum(RequestLog.cache_write_tokens), 0).label("cache_write_tokens"),
        func.coalesce(func.sum(RequestLog.cost), Decimal("0")).label("user_cost"),
        func.coalesce(func.sum(RequestLog.cost_amount), Decimal("0")).label("cost_amount"),
        func.avg(RequestLog.latency_ms).label("average_latency_ms"),
    )


def _metrics(row: dict[str, Any], *, include_internal_financials: bool) -> dict[str, Any]:
    average_latency = row["average_latency_ms"]
    metrics: dict[str, Any] = {
        "requests": int(row["requests"]),
        "failed_requests": int(row["failed_requests"]),
        "prompt_tokens": int(row["prompt_tokens"]),
        "completion_tokens": int(row["completion_tokens"]),
        "cache_read_tokens": int(row["cache_read_tokens"]),
        "cache_write_tokens": int(row["cache_write_tokens"]),
        "user_cost": row["user_cost"],
        "average_latency_ms": (
            int(round(average_latency)) if average_latency is not None else None
        ),
    }
    if include_internal_financials:
        metrics["cost_amount"] = row["cost_amount"]
        metrics["gross_profit"] = row["user_cost"] - row["cost_amount"]
    return metrics


async def _daily_usage(
    session: AsyncSession,
    *,
    conditions: list[Any],
    start_at: datetime,
    end_at: datetime,
    include_internal_financials: bool,
) -> list[dict[str, Any]]:
    daily_date = func.date(RequestLog.created_at).label("date")
    rows = (
        (
            await session.execute(
                select(daily_date, *_aggregate_columns())
                .where(*conditions)
                .group_by(daily_date)
                .order_by(daily_date)
            )
        )
        .mappings()
        .all()
    )
    by_date = {
        row["date"]: {
            "date": row["date"],
            **_metrics(dict(row), include_internal_financials=include_internal_financials),
        }
        for row in rows
    }
    points: list[dict[str, Any]] = []
    current_date = start_at.date()
    while current_date <= end_at.date():
        points.append(
            by_date.get(
                current_date,
                {
                    "date": current_date,
                    "requests": 0,
                    "failed_requests": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "user_cost": Decimal("0"),
                    **(
                        {"cost_amount": Decimal("0"), "gross_profit": Decimal("0")}
                        if include_internal_financials
                        else {}
                    ),
                    "average_latency_ms": None,
                },
            )
        )
        current_date += timedelta(days=1)
    return points


async def _dimension_stats(
    session: AsyncSession,
    *,
    conditions: list[Any],
    dimension_id: Any,
    dimension_name: Any,
    join_target: Any,
    join_condition: Any,
    missing_name: str,
    include_internal_financials: bool,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(
                    dimension_id.label("id"),
                    func.coalesce(dimension_name, literal(missing_name)).label("name"),
                    *_aggregate_columns(),
                )
                .select_from(RequestLog)
                .outerjoin(join_target, join_condition)
                .where(*conditions)
                .group_by(dimension_id, dimension_name)
                .order_by(func.sum(RequestLog.cost).desc(), dimension_id.asc())
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            **_metrics(dict(row), include_internal_financials=include_internal_financials),
        }
        for row in rows
    ]


async def _statistics(
    session: AsyncSession,
    *,
    start_at: datetime,
    end_at: datetime,
    owner_user_id: int | None,
    provider_ids: list[int],
    model_ids: list[int],
    api_key_ids: list[int],
    include_internal_financials: bool,
) -> dict[str, Any]:
    conditions = _filters(
        start_at=start_at,
        end_at=end_at,
        owner_user_id=owner_user_id,
        provider_ids=provider_ids,
        model_ids=model_ids,
        api_key_ids=api_key_ids,
    )
    total_row = (
        (await session.execute(select(*_aggregate_columns()).where(*conditions))).mappings().one()
    )
    result: dict[str, Any] = {
        "totals": _metrics(
            dict(total_row), include_internal_financials=include_internal_financials
        ),
        "daily_usage": await _daily_usage(
            session,
            conditions=conditions,
            start_at=start_at,
            end_at=end_at,
            include_internal_financials=include_internal_financials,
        ),
        "model_stats": await _dimension_stats(
            session,
            conditions=conditions,
            dimension_id=RequestLog.model_id,
            dimension_name=func.coalesce(Model.display_name, Model.canonical_name),
            join_target=Model,
            join_condition=Model.id == RequestLog.model_id,
            missing_name="未关联模型",
            include_internal_financials=include_internal_financials,
        ),
        "api_key_stats": await _dimension_stats(
            session,
            conditions=conditions,
            dimension_id=RequestLog.api_key_id,
            dimension_name=ApiKey.name,
            join_target=ApiKey,
            join_condition=ApiKey.id == RequestLog.api_key_id,
            missing_name="未关联 API Key",
            include_internal_financials=include_internal_financials,
        ),
    }
    if include_internal_financials:
        result["provider_stats"] = await _dimension_stats(
            session,
            conditions=conditions,
            dimension_id=RequestLog.provider_id,
            dimension_name=Provider.name,
            join_target=Provider,
            join_condition=Provider.id == RequestLog.provider_id,
            missing_name="未关联供应商",
            include_internal_financials=True,
        )
    return result


@admin_router.get("", response_model=AdminBillingStatisticsResponse)
async def get_admin_billing_statistics(
    session: Session,
    _: AdminUser,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
    provider_ids: Annotated[list[int] | None, Query()] = None,
    model_ids: Annotated[list[int] | None, Query()] = None,
    api_key_ids: Annotated[list[int] | None, Query()] = None,
) -> AdminBillingStatisticsResponse:
    start, end = _normalise_range(start_at, end_at)
    return AdminBillingStatisticsResponse(
        **await _statistics(
            session,
            start_at=start,
            end_at=end,
            owner_user_id=None,
            provider_ids=_normalise_ids(provider_ids),
            model_ids=_normalise_ids(model_ids),
            api_key_ids=_normalise_ids(api_key_ids),
            include_internal_financials=True,
        )
    )


@user_router.get("", response_model=UserBillingStatisticsResponse)
async def get_user_billing_statistics(
    session: Session,
    user: CurrentUser,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
    model_ids: Annotated[list[int] | None, Query()] = None,
    api_key_ids: Annotated[list[int] | None, Query()] = None,
) -> UserBillingStatisticsResponse:
    start, end = _normalise_range(start_at, end_at)
    return UserBillingStatisticsResponse(
        **await _statistics(
            session,
            start_at=start,
            end_at=end,
            owner_user_id=user.id,
            provider_ids=[],
            model_ids=_normalise_ids(model_ids),
            api_key_ids=_normalise_ids(api_key_ids),
            include_internal_financials=False,
        )
    )
