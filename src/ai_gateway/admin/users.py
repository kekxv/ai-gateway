from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ai_gateway.auth.dependencies import admin_user
from ai_gateway.auth.service import raise_auth_error
from ai_gateway.core.security import hash_password
from ai_gateway.db.models import Account, User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

Session = Annotated[AsyncSession, Depends(get_session)]
AdminUser = Annotated[User, Depends(admin_user)]
UserRole = Literal["admin", "user"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: SecretStr
    role: UserRole = "user"
    initial_balance: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=8)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=3, max_length=320)
    password: SecretStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    balance: Decimal
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: Session, _: AdminUser) -> UserResponse:
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password.get_secret_value()),
        role=payload.role,
    )
    user.account = Account(balance=payload.initial_balance)
    session.add(user)
    try:
        await session.flush()
        await session.refresh(user, attribute_names=["created_at", "updated_at"])
        response = _user_response(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "email_exists",
            "A user with this email already exists",
        )
    return response


@router.get("", response_model=list[UserResponse])
async def list_users(session: Session, _: AdminUser) -> list[UserResponse]:
    users = (
        await session.scalars(select(User).options(joinedload(User.account)).order_by(User.id))
    ).all()
    return [_user_response(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: Session, _: AdminUser) -> UserResponse:
    return _user_response(await _get_user(session, user_id))


@router.patch("/{user_id}", response_model=UserResponse)
@router.put("/{user_id}", response_model=UserResponse, include_in_schema=False)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: Session,
    _: AdminUser,
) -> UserResponse:
    user = await _get_user(session, user_id)
    if payload.email is not None:
        user.email = payload.email
    if payload.password is not None:
        user.password_hash = hash_password(payload.password.get_secret_value())
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    try:
        await session.flush()
        await session.refresh(user, attribute_names=["updated_at"])
        response = _user_response(user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise_auth_error(
            status.HTTP_409_CONFLICT,
            "email_exists",
            "A user with this email already exists",
        )
    return response


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, session: Session, _: AdminUser) -> Response:
    user = await _get_user(session, user_id)
    await session.delete(user)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_user(session: AsyncSession, user_id: int) -> User:
    user = await session.scalar(
        select(User).where(User.id == user_id).options(joinedload(User.account))
    )
    if user is None:
        raise_auth_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found")
    return user


def _user_response(user: User) -> UserResponse:
    if user.account is None:
        raise RuntimeError("managed user is missing an account")
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        balance=user.account.balance,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
