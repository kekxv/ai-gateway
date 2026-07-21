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
        return (await service.handle(request, Protocol.OPENAI)).response()
    except Exception as exc:
        return native_error_response(Protocol.OPENAI, exc)
