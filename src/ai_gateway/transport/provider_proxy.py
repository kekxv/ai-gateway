from __future__ import annotations

import re
from typing import Annotated, Literal

import httpx
import orjson
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from ai_gateway.core.config import Settings
from ai_gateway.core.security import decrypt_secret, encrypt_secret

_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_DISALLOWED_PROXY_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ProviderProxyInherit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["inherit"] = "inherit"


class ProviderProxyDirect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["direct"]


class ProviderProxyBasicAuth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["basic"]
    username: str = Field(min_length=1, max_length=1024, repr=False)
    password: str = Field(min_length=1, max_length=4096, repr=False)

    @field_validator("username", "password")
    @classmethod
    def validate_basic_value(cls, value: str) -> str:
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            raise ValueError("Proxy Basic credentials cannot contain control characters")
        return value


class ProviderProxyHeaderAuth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["headers"]
    headers: dict[str, str] = Field(min_length=1, max_length=32, repr=False)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        for name, value in headers.items():
            if (
                not name
                or len(name) > 128
                or _HEADER_NAME.fullmatch(name) is None
                or name.casefold() in _DISALLOWED_PROXY_HEADERS
            ):
                raise ValueError("Proxy authentication contains an invalid header name")
            if (
                not value
                or len(value) > 8192
                or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
            ):
                raise ValueError("Proxy authentication contains an invalid header value")
        return headers


ProviderProxyAuth = Annotated[
    ProviderProxyBasicAuth | ProviderProxyHeaderAuth,
    Field(discriminator="type"),
]


class ProviderProxyCustom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["custom"]
    url: str = Field(min_length=1, max_length=2048)
    auth: ProviderProxyAuth | None = Field(default=None, repr=False)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        raw = value.strip()
        try:
            url = httpx.URL(raw)
        except Exception:
            raise ValueError("Proxy URL is invalid") from None
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("Proxy URL must use http or https and include a host")
        if url.userinfo:
            raise ValueError("Proxy URL must not contain credentials")
        if url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError("Proxy URL must not contain a path, query, or fragment")
        return str(url.copy_with(raw_path=b""))


ProviderProxyConfig = Annotated[
    ProviderProxyInherit | ProviderProxyDirect | ProviderProxyCustom,
    Field(discriminator="mode"),
]
_PROXY_ADAPTER: TypeAdapter[ProviderProxyConfig] = TypeAdapter(ProviderProxyConfig)


class ProviderProxySummary(BaseModel):
    mode: Literal["inherit", "direct", "custom"]
    url: str | None = None
    auth_type: Literal["basic", "headers"] | None = None
    has_auth: bool = False


def proxy_summary(config: ProviderProxyConfig) -> ProviderProxySummary:
    if not isinstance(config, ProviderProxyCustom):
        return ProviderProxySummary(mode=config.mode)
    return ProviderProxySummary(
        mode="custom",
        url=config.url,
        auth_type=config.auth.type if config.auth is not None else None,
        has_auth=config.auth is not None,
    )


def to_httpx_proxy(config: ProviderProxyCustom) -> httpx.Proxy:
    if isinstance(config.auth, ProviderProxyBasicAuth):
        return httpx.Proxy(config.url, auth=(config.auth.username, config.auth.password))
    if isinstance(config.auth, ProviderProxyHeaderAuth):
        return httpx.Proxy(config.url, headers=config.auth.headers)
    return httpx.Proxy(config.url)


def encrypt_provider_proxy(config: ProviderProxyConfig, *, settings: Settings) -> bytes | None:
    if isinstance(config, ProviderProxyInherit):
        return None
    payload = orjson.dumps(config.model_dump(), option=orjson.OPT_SORT_KEYS).decode()
    return encrypt_secret(payload, settings=settings)


def decrypt_provider_proxy(
    encrypted: bytes | None,
    *,
    settings: Settings,
) -> ProviderProxyConfig:
    if encrypted is None:
        return ProviderProxyInherit()
    try:
        value = orjson.loads(decrypt_secret(encrypted, settings=settings))
        return _PROXY_ADAPTER.validate_python(value)
    except Exception:
        raise ValueError("Provider proxy configuration could not be decoded") from None


def validate_proxy_websocket_compatibility(
    config: ProviderProxyConfig,
    websocket_urls: list[str | None],
) -> None:
    if not any(websocket_urls) or not isinstance(config, ProviderProxyCustom):
        return
    if isinstance(config.auth, ProviderProxyHeaderAuth):
        raise ValueError("WebSocket proxy does not support custom authentication headers")
    if isinstance(config.auth, ProviderProxyBasicAuth):
        username = config.auth.username
        password = config.auth.password
        if (
            not username.isascii()
            or not password.isascii()
            or any(character in username for character in ":/?#[]")
            or any(character in password for character in "/?#[]")
        ):
            raise ValueError("Proxy Basic credentials are not compatible with WebSocket endpoints")
