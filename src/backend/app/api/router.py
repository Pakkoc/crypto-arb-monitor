"""Main API router — aggregates all sub-routers under /api/v1/."""
from __future__ import annotations

from fastapi import APIRouter

from app.api import alerts, exchanges, health, prices, spreads

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(exchanges.router, tags=["exchanges"])
api_router.include_router(prices.router, tags=["prices"])
api_router.include_router(spreads.router, tags=["spreads"])
api_router.include_router(alerts.router, tags=["alerts"])
