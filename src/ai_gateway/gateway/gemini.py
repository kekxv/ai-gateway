from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ai_gateway.core.enums import Protocol
from ai_gateway.gateway.dependencies import get_gateway_service
from ai_gateway.gateway.service import GatewayService, native_error_response

router = APIRouter()


@router.post("/v1beta/models/{model}:generateContent")
async def generate_content(
    model: str,
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    try:
        return (await service.handle(request, Protocol.GEMINI, path_model=model)).response()
    except Exception as exc:
        return native_error_response(Protocol.GEMINI, exc)


@router.post("/v1beta/models/{model}:streamGenerateContent")
async def stream_generate_content(
    model: str,
    request: Request,
    service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> Response:
    try:
        return (
            await service.handle(
                request,
                Protocol.GEMINI,
                path_model=model,
                force_stream=True,
            )
        ).response()
    except Exception as exc:
        return native_error_response(Protocol.GEMINI, exc)
