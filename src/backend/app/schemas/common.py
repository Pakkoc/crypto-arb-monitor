"""Common response schemas: ResponseEnvelope, pagination, errors."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard success response envelope.

    Example::

        {"status": "ok", "data": {...}, "timestamp_ms": 1709107200000}
    """

    status: str = "ok"
    data: T
    timestamp_ms: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiError(BaseModel):
    """Standard error response envelope."""

    status: str = "error"
    error: ErrorDetail
    timestamp_ms: int


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response envelope."""

    status: str = "ok"
    data: list[T]
    pagination: PaginationMeta
    timestamp_ms: int
