from typing import Annotated

import pyotp
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai_gateway.auth.dependencies import current_user
from ai_gateway.auth.schemas import (
    AccessToken,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpSetupResponse,
)
from ai_gateway.auth.service import authenticate_user, raise_auth_error, refresh_access_token
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


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def setup_totp(
    user: CurrentUser,
    session: Session,
    settings: AppSettings,
) -> TotpSetupResponse:
    secret = pyotp.random_base32()
    user.totp_secret_encrypted = encrypt_secret(secret, settings=settings)
    user.totp_enabled = False
    await session.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
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
    if user.totp_secret_encrypted is None:
        raise_auth_error(
            status.HTTP_400_BAD_REQUEST,
            "totp_not_configured",
            "TOTP enrollment has not been started",
        )
    secret = decrypt_secret(user.totp_secret_encrypted, settings=settings)
    if not pyotp.TOTP(secret).verify(payload.code.get_secret_value(), valid_window=1):
        raise_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_totp",
            "Invalid TOTP code",
            authenticate=True,
        )
    user.totp_enabled = True
    await session.commit()
    return TotpConfirmResponse(totp_enabled=True)
