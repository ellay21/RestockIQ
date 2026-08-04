"""Health check router."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns HTTP 200 when the service is up and running.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
