from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import current_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.enums import RequestStatus
from ai_gateway.db.models import Account, ApiKey, RequestLog, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/me/dashboard", tags=["user-dashboard"])

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(current_user)]


def dashboard_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


DashboardNow = Annotated[datetime, Depends(dashboard_now)]


class DailyUsagePoint(BaseModel):
    date: date
    requests: int
    failures: int
    cost: Decimal


class UserDashboardSummary(BaseModel):
    balance: Decimal
    total_spent: Decimal
    active_api_keys: int
    requests_24h: int
    failed_requests_24h: int
    prompt_tokens_24h: int
    completion_tokens_24h: int
    cost_24h: Decimal
    average_latency_ms_24h: int | None
    daily_usage: list[DailyUsagePoint]


@router.get("/summary", response_model=UserDashboardSummary)
async def get_user_dashboard_summary(
    session: Session,
    user: CurrentUser,
    now: DashboardNow,
) -> UserDashboardSummary:
    account = await session.scalar(select(Account).where(Account.user_id == user.id))
    if account is None:
        raise_auth_error(
            status.HTTP_404_NOT_FOUND,
            "account_not_found",
            "Billing account not found",
        )

    cutoff_24h = now - timedelta(hours=24)
    first_daily_date = now.date() - timedelta(days=6)
    first_daily_midnight = datetime.combine(first_daily_date, time.min)

    active_api_keys = await session.scalar(
        select(func.count(ApiKey.id)).where(
            ApiKey.user_id == user.id,
            ApiKey.is_active.is_(True),
        )
    )

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
                func.avg(RequestLog.latency_ms),
            ).where(
                RequestLog.user_id == user.id,
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
                )
                .where(
                    RequestLog.user_id == user.id,
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
                ),
            )
        )

    average_latency = request_row[5]
    return UserDashboardSummary(
        balance=account.balance,
        total_spent=account.total_spent,
        active_api_keys=int(active_api_keys or 0),
        requests_24h=int(request_row[0]),
        failed_requests_24h=int(request_row[1]),
        prompt_tokens_24h=int(request_row[2]),
        completion_tokens_24h=int(request_row[3]),
        cost_24h=request_row[4],
        average_latency_ms_24h=(
            int(round(average_latency)) if average_latency is not None else None
        ),
        daily_usage=daily_usage,
    )
