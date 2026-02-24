from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from garage_agent.schemas.common import APIResponse, APIError


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error=APIError(
                code="HTTP_ERROR",
                message=exc.detail,
            ),
        ).model_dump(),
    )