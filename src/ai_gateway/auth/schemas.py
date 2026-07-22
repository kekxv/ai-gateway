from datetime import datetime

from pydantic import BaseModel, SecretStr


class LoginRequest(BaseModel):
    email: str
    password: SecretStr
    totp_code: SecretStr | None = None


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    updated_at: datetime


class TotpSetupResponse(BaseModel):
    otpauth_uri: str


class TotpSetupRequest(BaseModel):
    current_totp_code: SecretStr | None = None


class TotpConfirmRequest(BaseModel):
    code: SecretStr


class TotpConfirmResponse(BaseModel):
    totp_enabled: bool
