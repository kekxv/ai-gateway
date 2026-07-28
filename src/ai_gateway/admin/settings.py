from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import admin_user
from ai_gateway.db.models import RegistrationLock, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]


class RegistrationSetting(BaseModel):
    enabled: bool


class RegistrationSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


@router.get("/registration", response_model=RegistrationSetting)
async def get_registration_setting(
    session: Session,
    _: AdminUser,
) -> RegistrationSetting:
    enabled = await session.scalar(select(RegistrationLock.enabled).where(RegistrationLock.id == 1))
    return RegistrationSetting(enabled=True if enabled is None else enabled)


@router.patch("/registration", response_model=RegistrationSetting)
async def update_registration_setting(
    payload: RegistrationSettingUpdate,
    session: Session,
    _: AdminUser,
) -> RegistrationSetting:
    await session.execute(
        insert(RegistrationLock).values(id=1).on_duplicate_key_update(id=RegistrationLock.id)
    )
    registration = await session.scalar(
        select(RegistrationLock).where(RegistrationLock.id == 1).with_for_update()
    )
    if registration is None:
        raise RuntimeError("registration lock was not created")
    registration.enabled = payload.enabled
    await session.commit()
    return RegistrationSetting(enabled=registration.enabled)
