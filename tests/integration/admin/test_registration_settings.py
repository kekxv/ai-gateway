from httpx import AsyncClient


async def test_administrator_can_read_registration_setting(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/admin/settings/registration")

    assert response.status_code == 200
    assert response.json() == {"enabled": True}


async def test_regular_user_cannot_read_or_change_registration_setting(
    non_admin_client: AsyncClient,
) -> None:
    read = await non_admin_client.get("/admin/settings/registration")
    update = await non_admin_client.patch(
        "/admin/settings/registration",
        json={"enabled": False},
    )

    assert read.status_code == 403
    assert read.json()["detail"]["code"] == "admin_required"
    assert update.status_code == 403
    assert update.json()["detail"]["code"] == "admin_required"
