import gzip

import orjson

from ai_gateway.audit.codec import gunzip_json, gzip_json


def test_gzip_json_is_canonical_deterministic_and_round_trips() -> None:
    left = {"z": [3, 2, 1], "a": {"second": 2, "first": 1}}
    right = {"a": {"first": 1, "second": 2}, "z": [3, 2, 1]}

    left_encoded = gzip_json(left)
    right_encoded = gzip_json(right)

    assert left_encoded == right_encoded
    assert gzip.decompress(left_encoded) == orjson.dumps(left, option=orjson.OPT_SORT_KEYS)
    assert gunzip_json(left_encoded) == left
    assert left_encoded[4:8] == b"\x00\x00\x00\x00"


def test_gzip_json_truncates_on_a_valid_utf8_boundary_with_metadata() -> None:
    value = {"message": "🙂" * 40, "password": "already-redacted-before-codec"}

    decoded = gunzip_json(gzip_json(value, limit_bytes=37))

    assert decoded["truncated"] is True
    assert isinstance(decoded["detail"], str)
    assert len(decoded["detail"].encode("utf-8")) <= 37
    decoded["detail"].encode("utf-8").decode("utf-8")


def test_repetitive_payload_compresses_smaller_than_canonical_json() -> None:
    value = {"message": "repetitive audit payload " * 500}
    canonical = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)

    assert len(gzip_json(value)) < len(canonical)
