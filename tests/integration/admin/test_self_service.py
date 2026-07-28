from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.db.models import Model, ModelAlias


async def test_regular_user_sees_only_enabled_models_and_aliases(
    admin_client: AsyncClient,
    non_admin_client: AsyncClient,
    session: AsyncSession,
) -> None:
    available = Model(
        canonical_name="available-model",
        display_name="Available model",
        enabled=True,
        aliases=[
            ModelAlias(alias="available-alias", enabled=True),
            ModelAlias(alias="disabled-alias", enabled=False),
        ],
    )
    unavailable = Model(
        canonical_name="disabled-model",
        display_name="Disabled model",
        enabled=False,
        aliases=[ModelAlias(alias="hidden-alias", enabled=True)],
    )
    session.add_all([available, unavailable])
    await session.flush()

    user_response = await non_admin_client.get("/user/models")
    admin_response = await admin_client.get("/admin/models")

    assert user_response.status_code == 200
    assert [model["canonical_name"] for model in user_response.json()] == ["available-model"]
    assert [alias["alias"] for alias in user_response.json()[0]["aliases"]] == ["available-alias"]
    assert [model["canonical_name"] for model in admin_response.json()] == [
        "available-model",
        "disabled-model",
    ]
    assert [alias["alias"] for alias in admin_response.json()[0]["aliases"]] == [
        "available-alias",
        "disabled-alias",
    ]
