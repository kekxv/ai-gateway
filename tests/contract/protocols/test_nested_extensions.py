from __future__ import annotations

import orjson

from ai_gateway.protocols.registry import get_adapter


def test_openai_nested_extensions_round_trip_only_to_openai() -> None:
    payload = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "name": "alice",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [
            {
                "type": "function",
                "x-tool": "kept",
                "function": {"name": "f", "parameters": {}, "strict": True},
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "f"},
            "parallel": False,
        },
    }
    request = get_adapter("openai").decode_request(payload)
    same = get_adapter("openai").encode_request(request)

    assert same["messages"][0]["name"] == "alice"
    assert same["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tools"][0]["x-tool"] == "kept"
    assert same["tools"][0]["function"]["strict"] is True
    assert same["tool_choice"]["parallel"] is False
    assert b"cache_control" not in orjson.dumps(get_adapter("claude").encode_request(request))
    assert b"strict" not in orjson.dumps(get_adapter("gemini").encode_request(request))


def test_claude_cache_control_and_nested_extensions_do_not_leak() -> None:
    payload = {
        "model": "m",
        "max_tokens": 8,
        "system": [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {
                "role": "user",
                "vendor_message": "kept",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        "tools": [{"name": "f", "input_schema": {}, "cache_control": {"type": "ephemeral"}}],
        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
    }
    request = get_adapter("claude").decode_request(payload)
    same = get_adapter("claude").encode_request(request)

    assert same["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["messages"][0]["vendor_message"] == "kept"
    assert same["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert same["tool_choice"]["disable_parallel_tool_use"] is True
    assert b"cache_control" not in orjson.dumps(get_adapter("openai").encode_request(request))
    assert b"vendor_message" not in orjson.dumps(get_adapter("gemini").encode_request(request))


def test_gemini_nested_and_generation_extensions_do_not_leak() -> None:
    payload = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "vendorMessage": "kept",
                "parts": [{"text": "hi", "thoughtSignature": "signature"}],
            }
        ],
        "tools": [
            {
                "vendorGroup": "kept",
                "functionDeclarations": [{"name": "f", "parameters": {}, "behavior": "BLOCKING"}],
            }
        ],
        "toolConfig": {
            "functionCallingConfig": {"mode": "AUTO", "vendorCalling": "kept"},
            "vendorToolConfig": "kept",
        },
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    request = get_adapter("gemini").decode_request(payload)
    same = get_adapter("gemini").encode_request(request)

    assert same["contents"][0]["vendorMessage"] == "kept"
    assert same["contents"][0]["parts"][0]["thoughtSignature"] == "signature"
    assert same["tools"][0]["vendorGroup"] == "kept"
    assert same["tools"][0]["functionDeclarations"][0]["behavior"] == "BLOCKING"
    assert same["toolConfig"]["functionCallingConfig"]["vendorCalling"] == "kept"
    assert same["toolConfig"]["vendorToolConfig"] == "kept"
    assert same["generationConfig"]["responseMimeType"] == "application/json"
    assert b"thoughtSignature" not in orjson.dumps(get_adapter("openai").encode_request(request))
    assert b"responseMimeType" not in orjson.dumps(get_adapter("claude").encode_request(request))
