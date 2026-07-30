from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import admin_user
from ai_gateway.core.enums import RequestStatus, RouteRuntimeState
from ai_gateway.db.models import ApiKey, Model, ModelRoute, Provider, RequestLog, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]


def dashboard_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


DashboardNow = Annotated[datetime, Depends(dashboard_now)]


class ResourceCount(BaseModel):
    total: int
    enabled: int


class RouteCount(ResourceCount):
    unavailable: int


class DailyUsagePoint(BaseModel):
    date: date
    requests: int
    failures: int
    cost: Decimal
    cost_amount: Decimal
    gross_profit: Decimal


class DashboardSummary(BaseModel):
    users_total: int
    active_api_keys: int
    providers: ResourceCount
    models: ResourceCount
    routes: RouteCount
    requests_24h: int
    failed_requests_24h: int
    prompt_tokens_24h: int
    completion_tokens_24h: int
    cost_24h: Decimal
    cost_amount_24h: Decimal
    gross_profit_24h: Decimal
    average_latency_ms_24h: int | None
    daily_usage: list[DailyUsagePoint]


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    session: Session,
    _: AdminUser,
    now: DashboardNow,
) -> DashboardSummary:
    cutoff_24h = now - timedelta(hours=24)
    first_daily_date = now.date() - timedelta(days=6)
    first_daily_midnight = datetime.combine(first_daily_date, time.min)

    users_total = await session.scalar(select(func.count(User.id)))
    active_api_keys = await session.scalar(
        select(func.count(ApiKey.id)).where(ApiKey.is_active.is_(True))
    )

    provider_row = (
        await session.execute(
            select(
                func.count(Provider.id),
                func.coalesce(
                    func.sum(case((Provider.enabled.is_(True), 1), else_=0)),
                    0,
                ),
            )
        )
    ).one()
    model_row = (
        await session.execute(
            select(
                func.count(Model.id),
                func.coalesce(
                    func.sum(case((Model.enabled.is_(True), 1), else_=0)),
                    0,
                ),
            )
        )
    ).one()
    route_row = (
        await session.execute(
            select(
                func.count(ModelRoute.id),
                func.coalesce(
                    func.sum(case((ModelRoute.enabled.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (ModelRoute.runtime_state == RouteRuntimeState.OPEN, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
        )
    ).one()

    request_row = (
        await session.execute(
            select(
                func.count(RequestLog.id),
                func.coalesce(
                    func.sum(
                        case(
                            (RequestLog.status == RequestStatus.FAILED, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(RequestLog.prompt_tokens), 0),
                func.coalesce(func.sum(RequestLog.completion_tokens), 0),
                func.coalesce(func.sum(RequestLog.cost), Decimal("0")),
                func.coalesce(func.sum(RequestLog.cost_amount), Decimal("0")),
                func.avg(RequestLog.latency_ms),
            ).where(
                RequestLog.created_at >= cutoff_24h,
                RequestLog.created_at <= now,
            )
        )
    ).one()

    daily_date = func.date(RequestLog.created_at).label("date")
    daily_rows = (
        (
            await session.execute(
                select(
                    daily_date,
                    func.count(RequestLog.id).label("requests"),
                    func.coalesce(
                        func.sum(
                            case(
                                (RequestLog.status == RequestStatus.FAILED, 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("failures"),
                    func.coalesce(func.sum(RequestLog.cost), Decimal("0")).label("cost"),
                    func.coalesce(func.sum(RequestLog.cost_amount), Decimal("0")).label(
                        "cost_amount"
                    ),
                )
                .where(
                    RequestLog.created_at >= first_daily_midnight,
                    RequestLog.created_at <= now,
                )
                .group_by(daily_date)
                .order_by(daily_date)
            )
        )
        .mappings()
        .all()
    )
    daily_by_date = {
        row["date"]: DailyUsagePoint(
            date=row["date"],
            requests=int(row["requests"]),
            failures=int(row["failures"]),
            cost=row["cost"],
            cost_amount=row["cost_amount"],
            gross_profit=row["cost"] - row["cost_amount"],
        )
        for row in daily_rows
    }
    daily_usage: list[DailyUsagePoint] = []
    for offset in range(7):
        current_date = first_daily_date + timedelta(days=offset)
        daily_usage.append(
            daily_by_date.get(
                current_date,
                DailyUsagePoint(
                    date=current_date,
                    requests=0,
                    failures=0,
                    cost=Decimal("0"),
                    cost_amount=Decimal("0"),
                    gross_profit=Decimal("0"),
                ),
            )
        )

    average_latency = request_row[6]
    return DashboardSummary(
        users_total=int(users_total or 0),
        active_api_keys=int(active_api_keys or 0),
        providers=ResourceCount(total=int(provider_row[0]), enabled=int(provider_row[1])),
        models=ResourceCount(total=int(model_row[0]), enabled=int(model_row[1])),
        routes=RouteCount(
            total=int(route_row[0]),
            enabled=int(route_row[1]),
            unavailable=int(route_row[2]),
        ),
        requests_24h=int(request_row[0]),
        failed_requests_24h=int(request_row[1]),
        prompt_tokens_24h=int(request_row[2]),
        completion_tokens_24h=int(request_row[3]),
        cost_24h=request_row[4],
        cost_amount_24h=request_row[5],
        gross_profit_24h=request_row[4] - request_row[5],
        average_latency_ms_24h=(
            int(round(average_latency)) if average_latency is not None else None
        ),
        daily_usage=daily_usage,
    )
