from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(protocol: str, name: str) -> dict[str, Any]:
        with (FIXTURES / protocol / name).open(encoding="utf-8") as fixture:
            value = json.load(fixture)
        assert isinstance(value, dict)
        return value

    return _load


@pytest.fixture
def load_bytes():
    def _load(protocol: str, name: str) -> bytes:
        return (FIXTURES / protocol / name).read_bytes()

    return _load
