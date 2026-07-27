from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ai_gateway.core.enums import Protocol
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.service import GatewayService, native_error_response

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/chat/completions",
                openai_operation="chat_completions",
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/responses")
async def responses(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Responses API - unified interface for chat completions and other features."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/responses",
                openai_operation="responses",
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Embeddings API - generate text embeddings."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/embeddings",
                openai_operation="embeddings",
                required_protocol=Protocol.OPENAI,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)


@router.post("/v1/completions")
async def completions(
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    """OpenAI Completions API (Legacy) - text completions."""
    try:
        return (
            await service.handle(
                request,
                Protocol.OPENAI,
                endpoint_path="/v1/completions",
                openai_operation="completions",
                required_protocol=Protocol.OPENAI,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)
