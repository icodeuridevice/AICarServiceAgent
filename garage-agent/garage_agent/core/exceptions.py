from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from garage_agent.schemas.common import APIResponse, APIError
from garage_agent.core.error_codes import ErrorCode

from garage_agent.core.domain_exceptions import DomainException


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error=APIError(
                code=ErrorCode.VALIDATION_ERROR,
                message=str(exc.detail),
            ),
        ).model_dump(),
    )

async def domain_exception_handler(request: Request, exc: DomainException):
    return JSONResponse(
        status_code=400,
        content=APIResponse(
            success=False,
            error=APIError(
                code=exc.code,
                message=exc.message,
            ),
        ).model_dump(),
    )    