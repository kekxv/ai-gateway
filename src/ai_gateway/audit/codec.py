from __future__ import annotations

import gzip
from collections.abc import Mapping
from typing import Any, cast

import orjson

DEFAULT_AUDIT_BODY_LIMIT_BYTES = 1_048_576


def gzip_json(
    value: Mapping[str, Any],
    *,
    limit_bytes: int | None = None,
) -> bytes:
    """Serialize canonical JSON and return deterministic level-six GZIP bytes."""

    payload = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    limit = DEFAULT_AUDIT_BODY_LIMIT_BYTES if limit_bytes is None else limit_bytes
    if limit < 1:
        raise ValueError("limit_bytes must be positive")
    if len(payload) > limit:
        detail = payload[:limit].decode("utf-8", errors="ignore")
        payload = orjson.dumps(
            {"detail": detail, "truncated": True},
            option=orjson.OPT_SORT_KEYS,
        )
    return gzip.compress(payload, compresslevel=6, mtime=0)


def gunzip_json(value: bytes) -> dict[str, Any]:
    """Decompress one stored audit detail object."""

    decoded = orjson.loads(gzip.decompress(value))
    if not isinstance(decoded, dict):
        raise ValueError("audit detail must contain a JSON object")
    return cast(dict[str, Any], decoded)
