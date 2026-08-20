from datetime import datetime
from decimal import Decimal

from ai_gateway.admin.users import UserResponse


def test_api_timestamps_mark_naive_database_values_as_utc() -> None:
    response = UserResponse(
        id=1,
        email="user@example.com",
        role="user",
        is_active=True,
        balance=Decimal("0"),
        total_spent=Decimal("0"),
        created_at=datetime(2026, 8, 20, 8, 30, 0),
        updated_at=datetime(2026, 8, 20, 8, 30, 0),
    )

    assert response.model_dump(mode="json")["created_at"] == "2026-08-20T08:30:00+00:00"
