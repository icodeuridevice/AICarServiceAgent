from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIError(BaseModel):
    code: str
    message: str


class APIResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: APIError | None = None