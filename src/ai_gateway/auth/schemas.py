from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=8, max_length=1024)


class RegistrationStatusResponse(BaseModel):
    enabled: bool


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr
    new_password: SecretStr = Field(min_length=8, max_length=1024)


class TotpDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr
    code: SecretStr = Field(min_length=6, max_length=6)


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
