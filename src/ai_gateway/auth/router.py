from typing import Annotated

import pyotp
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import current_user
from ai_gateway.auth.schemas import (
    AccessToken,
    CurrentUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpDisableRequest,
    TotpSetupRequest,
    TotpSetupResponse,
)
from ai_gateway.auth.service import (
    authenticate_user,
    change_password,
    disable_totp,
    raise_auth_error,
    refresh_access_token,
    register_user,
)
from ai_gateway.core.config import Settings, get_settings
from ai_gateway.core.security import (
    decrypt_secret,
    encrypt_secret,
    issue_access_token,
    issue_refresh_token,
)
from ai_gateway.db.models import User
from ai_gateway.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(current_user)]


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: Session,
    settings: AppSettings,
) -> TokenPair:
    user = await register_user(
        session=session,
        email=payload.email,
        password=payload.password.get_secret_value(),
    )
    return TokenPair(
        access_token=issue_access_token(user_id=user.id, settings=settings),
        refresh_token=issue_refresh_token(user_id=user.id, settings=settings),
    )


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: Session, settings: AppSettings) -> TokenPair:
    user = await authenticate_user(
        session=session,
        email=payload.email,
        password=payload.password.get_secret_value(),
        totp_code=(payload.totp_code.get_secret_value() if payload.totp_code is not None else None),
        settings=settings,
    )
    return TokenPair(
        access_token=issue_access_token(user_id=user.id, settings=settings),
        refresh_token=issue_refresh_token(user_id=user.id, settings=settings),
    )


@router.post("/refresh", response_model=AccessToken)
async def refresh(
    payload: RefreshRequest,
    session: Session,
    settings: AppSettings,
) -> AccessToken:
    token = await refresh_access_token(
        session=session,
        refresh_token=payload.refresh_token.get_secret_value(),
        settings=settings,
    )
    return AccessToken(access_token=token)


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    session: Session,
) -> Response:
    await change_password(
        session=session,
        user_id=user.id,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/totp/disable", response_model=TotpConfirmResponse)
async def remove_totp(
    payload: TotpDisableRequest,
    user: CurrentUser,
    session: Session,
    settings: AppSettings,
) -> TotpConfirmResponse:
    await disable_totp(
        session=session,
        user_id=user.id,
        current_password=payload.current_password.get_secret_value(),
        code=payload.code.get_secret_value(),
        settings=settings,
    )
    return TotpConfirmResponse(totp_enabled=False)


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def setup_totp(
    user: CurrentUser,
    session: Session,
    settings: AppSettings,
    payload: TotpSetupRequest | None = None,
) -> TotpSetupResponse:
    locked_user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_user is None:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )
    if locked_user.totp_enabled:
        if payload is None or payload.current_totp_code is None:
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "current_totp_required",
                "The current TOTP code is required",
                authenticate=True,
            )
        if locked_user.totp_secret_encrypted is None:
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_totp",
                "Invalid TOTP code",
                authenticate=True,
            )
        active_secret = decrypt_secret(locked_user.totp_secret_encrypted, settings=settings)
        if not pyotp.TOTP(active_secret).verify(
            payload.current_totp_code.get_secret_value(),
            valid_window=1,
        ):
            raise_auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_totp",
                "Invalid TOTP code",
                authenticate=True,
            )
    secret = pyotp.random_base32()
    locked_user.pending_totp_secret_encrypted = encrypt_secret(secret, settings=settings)
    await session.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=locked_user.email,
        issuer_name=settings.jwt_issuer,
    )
    return TotpSetupResponse(otpauth_uri=uri)


@router.post("/totp/confirm", response_model=TotpConfirmResponse)
async def confirm_totp(
    payload: TotpConfirmRequest,
    user: CurrentUser,
    session: Session,
    settings: AppSettings,
) -> TotpConfirmResponse:
    locked_user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_user is None:
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "Invalid or expired token",
            authenticate=True,
        )
    if locked_user.pending_totp_secret_encrypted is None:
        raise_auth_error(
            status.HTTP_400_BAD_REQUEST,
            "totp_not_configured",
            "TOTP enrollment has not been started",
        )
    secret = decrypt_secret(locked_user.pending_totp_secret_encrypted, settings=settings)
    if not pyotp.TOTP(secret).verify(payload.code.get_secret_value(), valid_window=1):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_totp",
            "Invalid TOTP code",
            authenticate=True,
        )
    locked_user.totp_secret_encrypted = locked_user.pending_totp_secret_encrypted
    locked_user.pending_totp_secret_encrypted = None
    locked_user.totp_enabled = True
    await session.commit()
    return TotpConfirmResponse(totp_enabled=True)
