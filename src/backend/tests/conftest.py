"""Pytest configuration and shared fixtures.

Test implementations are added in Step 9 (Integration Testing).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import init_db, create_all_tables, close_engine


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Initialize an in-memory SQLite database for each test function."""
    init_db("sqlite+aiosqlite:///:memory:")
    await create_all_tables()
    yield
    await close_engine()


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """Async HTTP test client for the FastAPI application."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
