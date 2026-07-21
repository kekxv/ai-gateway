from __future__ import annotations

from ai_gateway.core.enums import Protocol
from ai_gateway.protocols.base import ProtocolAdapter
from ai_gateway.protocols.claude import ClaudeAdapter
from ai_gateway.protocols.gemini import GeminiAdapter
from ai_gateway.protocols.openai import OpenAIAdapter

_ADAPTERS: dict[Protocol, ProtocolAdapter] = {
    Protocol.OPENAI: OpenAIAdapter(),
    Protocol.CLAUDE: ClaudeAdapter(),
    Protocol.GEMINI: GeminiAdapter(),
}


def get_adapter(protocol: Protocol | str) -> ProtocolAdapter:
    return _ADAPTERS[Protocol(protocol)]
