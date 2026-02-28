"""Integration tests for the Crypto Arbitrage Monitor.

Verifies frontend-backend contract compliance:
- REST API health endpoint
- WebSocket connection and message protocol
- Alert CRUD operations
- Spread calculation logic with sample data

Usage:
    cd src/backend
    python -m pytest ../../tests/test_integration.py -v
    # or directly:
    python ../../tests/test_integration.py

Requires:
    pip install httpx websockets pytest pytest-asyncio
    The FastAPI server must NOT be running (tests start their own).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from decimal import Decimal

import pytest
import httpx

# ---------------------------------------------------------------------------
# Ensure the backend package is importable
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "backend")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def tmp_db(tmp_path_factory):
    """Create a temporary database path for tests."""
    d = tmp_path_factory.mktemp("data")
    return str(d / "test_arb.db")


@pytest.fixture(scope="module")
def app(tmp_db):
    """Create a FastAPI app with a temporary database."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["TELEGRAM_BOT_TOKEN"] = ""  # Disable Telegram in tests
    os.environ["DEBUG"] = "false"

    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="module")
async def client(app):
    """Async HTTP client using httpx with ASGI transport."""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Health Endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Verify GET /api/v1/health returns expected structure."""

    @pytest.mark.anyio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "data" in body
        assert "timestamp_ms" in body

    @pytest.mark.anyio
    async def test_health_structure(self, client):
        resp = await client.get("/api/v1/health")
        data = resp.json()["data"]
        # Verify all top-level keys
        for key in ["server", "exchanges", "database", "fx_rate",
                     "tracked_symbols", "active_alerts", "dashboard_clients"]:
            assert key in data, f"Missing key: {key}"

        # Server sub-keys
        server = data["server"]
        assert "uptime_seconds" in server
        assert "version" in server
        assert "python_version" in server
        assert "started_at" in server

        # Exchanges sub-keys
        exchanges = data["exchanges"]
        assert "total" in exchanges
        assert "connected" in exchanges
        assert "disconnected" in exchanges

        # Database sub-keys
        db = data["database"]
        assert "status" in db
        assert "size_mb" in db


# ---------------------------------------------------------------------------
# 2. Exchange Status Endpoint
# ---------------------------------------------------------------------------

class TestExchangeEndpoint:
    """Verify GET /api/v1/exchanges returns exchange connection data."""

    @pytest.mark.anyio
    async def test_exchanges_returns_ok(self, client):
        resp = await client.get("/api/v1/exchanges")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# 3. Prices Endpoint
# ---------------------------------------------------------------------------

class TestPricesEndpoint:
    """Verify GET /api/v1/prices returns valid structure."""

    @pytest.mark.anyio
    async def test_prices_returns_ok(self, client):
        resp = await client.get("/api/v1/prices")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        data = body["data"]
        assert "prices" in data
        assert "fx_rate" in data
        assert isinstance(data["prices"], list)


# ---------------------------------------------------------------------------
# 4. Spreads Endpoint
# ---------------------------------------------------------------------------

class TestSpreadsEndpoint:
    """Verify GET /api/v1/spreads returns valid structure."""

    @pytest.mark.anyio
    async def test_spreads_returns_ok(self, client):
        resp = await client.get("/api/v1/spreads")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        data = body["data"]
        assert "spreads" in data
        assert isinstance(data["spreads"], list)


# ---------------------------------------------------------------------------
# 5. Alert CRUD
# ---------------------------------------------------------------------------

class TestAlertCrud:
    """Verify full alert configuration CRUD lifecycle."""

    @pytest.mark.anyio
    async def test_list_alerts_initially_empty(self, client):
        resp = await client.get("/api/v1/alerts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["data"], list)
        assert "pagination" in body

    @pytest.mark.anyio
    async def test_create_alert(self, client):
        payload = {
            "chat_id": 0,
            "symbol": "BTC",
            "threshold_pct": 2.5,
            "direction": "above",
            "cooldown_minutes": 5,
            "enabled": True,
        }
        resp = await client.post("/api/v1/alerts", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "ok"
        alert = body["data"]
        assert alert["symbol"] == "BTC"
        assert alert["threshold_pct"] == "2.50"
        assert alert["direction"] == "above"
        assert alert["enabled"] is True
        assert alert["cooldown_minutes"] == 5
        return alert["id"]

    @pytest.mark.anyio
    async def test_get_alert_by_id(self, client):
        # Create first
        payload = {
            "symbol": "ETH",
            "threshold_pct": 1.5,
            "direction": "both",
        }
        create_resp = await client.post("/api/v1/alerts", json=payload)
        alert_id = create_resp.json()["data"]["id"]

        # Read
        resp = await client.get(f"/api/v1/alerts/{alert_id}")
        assert resp.status_code == 200
        alert = resp.json()["data"]
        assert alert["id"] == alert_id
        assert alert["symbol"] == "ETH"

    @pytest.mark.anyio
    async def test_update_alert(self, client):
        # Create
        create_resp = await client.post("/api/v1/alerts", json={
            "symbol": "SOL",
            "threshold_pct": 3.0,
            "direction": "above",
        })
        alert_id = create_resp.json()["data"]["id"]

        # Update
        resp = await client.put(f"/api/v1/alerts/{alert_id}", json={
            "threshold_pct": 4.0,
            "direction": "below",
            "enabled": False,
        })
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["threshold_pct"] == "4.00"
        assert updated["direction"] == "below"
        assert updated["enabled"] is False

    @pytest.mark.anyio
    async def test_delete_alert(self, client):
        # Create
        create_resp = await client.post("/api/v1/alerts", json={
            "symbol": "XRP",
            "threshold_pct": 1.0,
            "direction": "both",
        })
        alert_id = create_resp.json()["data"]["id"]

        # Delete
        resp = await client.delete(f"/api/v1/alerts/{alert_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_id"] == alert_id

        # Verify gone
        resp = await client.get(f"/api/v1/alerts/{alert_id}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_create_alert_validation_error(self, client):
        """Threshold out of range should return 422."""
        payload = {
            "threshold_pct": 100.0,  # max is 50.0
            "direction": "above",
        }
        resp = await client.post("/api/v1/alerts", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Symbols & Preferences Endpoints
# ---------------------------------------------------------------------------

class TestSymbolsAndPreferences:
    """Verify symbol listing and preference endpoints."""

    @pytest.mark.anyio
    async def test_list_symbols(self, client):
        resp = await client.get("/api/v1/symbols")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    @pytest.mark.anyio
    async def test_get_preferences(self, client):
        resp = await client.get("/api/v1/preferences")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "dashboard" in data
        assert "notifications" in data

    @pytest.mark.anyio
    async def test_fx_rate_endpoint(self, client):
        resp = await client.get("/api/v1/fx-rate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "rate" in data
        assert "source" in data
        assert "is_stale" in data


# ---------------------------------------------------------------------------
# 7. WebSocket Protocol (via httpx ASGI transport)
# ---------------------------------------------------------------------------

class TestWebSocketProtocol:
    """Verify WebSocket message protocol matches frontend expectations."""

    @pytest.mark.anyio
    async def test_ws_welcome_and_subscribe(self, app):
        """Test the full WS handshake: connect -> welcome -> subscribe -> snapshot."""
        from starlette.testclient import TestClient

        # Use synchronous TestClient for WebSocket testing
        with TestClient(app) as tc:
            with tc.websocket_connect("/api/v1/ws") as ws:
                # 1. Receive welcome message
                welcome = ws.receive_json()
                assert welcome["type"] == "welcome"
                assert "data" in welcome
                assert "server_version" in welcome["data"]
                assert "available_symbols" in welcome["data"]
                assert "exchanges" in welcome["data"]
                assert "heartbeat_interval_ms" in welcome["data"]
                assert isinstance(welcome["seq"], int)
                assert welcome["seq"] == 1

                # 2. Send subscribe
                ws.send_json({
                    "type": "subscribe",
                    "symbols": ["BTC", "ETH"],
                    "channels": ["prices", "spreads", "alerts", "exchange_status"],
                })

                # 3. Receive subscribed confirmation
                subscribed = ws.receive_json()
                assert subscribed["type"] == "subscribed"
                assert set(subscribed["data"]["symbols"]) == {"BTC", "ETH"}

                # 4. Receive snapshot
                snapshot = ws.receive_json()
                assert snapshot["type"] == "snapshot"
                data = snapshot["data"]
                assert "prices" in data
                assert "spreads" in data
                assert "exchange_statuses" in data
                assert "fx_rate" in data
                assert isinstance(data["prices"], list)
                assert isinstance(data["spreads"], list)
                assert isinstance(data["exchange_statuses"], list)

    @pytest.mark.anyio
    async def test_ws_pong_response(self, app):
        """Test that sending a pong message does not cause errors."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/api/v1/ws") as ws:
                # Consume welcome
                ws.receive_json()

                # Send pong (client acknowledges heartbeat)
                ws.send_json({"type": "pong"})

                # Send unknown message type -> should get error response
                ws.send_json({"type": "invalid_type"})
                error = ws.receive_json()
                assert error["type"] == "error"
                assert error["data"]["code"] == "UNKNOWN_MESSAGE_TYPE"


# ---------------------------------------------------------------------------
# 8. Spread Calculation Logic
# ---------------------------------------------------------------------------

class TestSpreadCalculation:
    """Verify spread calculation math with sample data."""

    def test_same_currency_spread(self):
        """Same-currency spread: (price_a / price_b - 1) * 100."""
        from app.schemas.price import TickerUpdate
        from app.services.price_store import PriceStore
        from app.services.spread_calculator import SpreadCalculator

        ps = PriceStore()
        sc = SpreadCalculator(ps)

        # Bithumb BTC = 95,000,000 KRW
        tick_a = TickerUpdate(
            exchange="bithumb", symbol="BTC", price=Decimal("95000000"),
            currency="KRW", volume_24h=Decimal("100"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )
        # Upbit BTC = 94,500,000 KRW
        tick_b = TickerUpdate(
            exchange="upbit", symbol="BTC", price=Decimal("94500000"),
            currency="KRW", volume_24h=Decimal("200"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )

        ps.update(tick_a)
        ps.update(tick_b)

        result = sc._compute_pair("bithumb", "upbit", "BTC")
        assert result is not None
        assert result.spread_type == "same_currency"
        # (95000000 / 94500000 - 1) * 100 ≈ 0.53%
        assert float(result.spread_pct) == pytest.approx(0.53, abs=0.01)

    def test_kimchi_premium_spread(self):
        """Kimchi premium: (KRW_price / (USDT_price * fx_rate) - 1) * 100."""
        from app.schemas.price import TickerUpdate
        from app.services.price_store import PriceStore
        from app.services.spread_calculator import SpreadCalculator

        ps = PriceStore()
        sc = SpreadCalculator(ps)

        # Set FX rate: 1 USDT = 1,350 KRW
        ps.update_fx_fallback(Decimal("1350"), "test")

        # Bithumb BTC = 95,000,000 KRW
        tick_krw = TickerUpdate(
            exchange="bithumb", symbol="BTC", price=Decimal("95000000"),
            currency="KRW", volume_24h=Decimal("100"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )
        # Binance BTC = 68,500 USDT
        tick_usd = TickerUpdate(
            exchange="binance", symbol="BTC", price=Decimal("68500"),
            currency="USDT", volume_24h=Decimal("500"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )

        ps.update(tick_krw)
        ps.update(tick_usd)

        result = sc._compute_pair("bithumb", "binance", "BTC")
        assert result is not None
        assert result.spread_type == "kimchi_premium"
        assert result.fx_rate == Decimal("1350")
        # (95000000 / (68500 * 1350) - 1) * 100 ≈ 2.74%
        expected = (95000000 / (68500 * 1350) - 1) * 100
        assert float(result.spread_pct) == pytest.approx(expected, abs=0.1)

    def test_spread_without_fx_returns_none(self):
        """Kimchi premium without FX rate should return None."""
        from app.schemas.price import TickerUpdate
        from app.services.price_store import PriceStore
        from app.services.spread_calculator import SpreadCalculator

        ps = PriceStore()
        sc = SpreadCalculator(ps)

        # No FX rate set
        tick_krw = TickerUpdate(
            exchange="bithumb", symbol="BTC", price=Decimal("95000000"),
            currency="KRW", volume_24h=Decimal("100"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )
        tick_usd = TickerUpdate(
            exchange="binance", symbol="BTC", price=Decimal("68500"),
            currency="USDT", volume_24h=Decimal("500"), timestamp_ms=int(1e13),
            received_at_ms=int(1e13),
        )
        ps.update(tick_krw)
        ps.update(tick_usd)

        result = sc._compute_pair("bithumb", "binance", "BTC")
        assert result is None  # Cannot compute without FX rate


# ---------------------------------------------------------------------------
# 9. Alert Severity Classification
# ---------------------------------------------------------------------------

class TestAlertSeverity:
    """Verify alert severity tier classification."""

    def test_severity_tiers(self):
        from app.services.alert_engine import classify_severity
        from app.utils.enums import AlertSeverity

        assert classify_severity(Decimal("0.5")) is None       # Below info
        assert classify_severity(Decimal("1.0")) == AlertSeverity.INFO
        assert classify_severity(Decimal("1.5")) == AlertSeverity.INFO
        assert classify_severity(Decimal("2.0")) == AlertSeverity.WARNING
        assert classify_severity(Decimal("2.9")) == AlertSeverity.WARNING
        assert classify_severity(Decimal("3.0")) == AlertSeverity.CRITICAL
        assert classify_severity(Decimal("5.0")) == AlertSeverity.CRITICAL

    def test_severity_negative_values(self):
        """Severity uses abs() so negative spreads also classify."""
        from app.services.alert_engine import classify_severity
        from app.utils.enums import AlertSeverity

        assert classify_severity(Decimal("-3.5")) == AlertSeverity.CRITICAL
        assert classify_severity(Decimal("-2.0")) == AlertSeverity.WARNING
        assert classify_severity(Decimal("-0.5")) is None


# ---------------------------------------------------------------------------
# 10. Enum Consistency (Frontend ↔ Backend)
# ---------------------------------------------------------------------------

class TestEnumConsistency:
    """Verify TypeScript enum values match Python StrEnum values."""

    def test_exchange_ids(self):
        from app.utils.enums import ExchangeId
        expected = {"bithumb", "upbit", "coinone", "binance", "bybit"}
        assert {e.value for e in ExchangeId} == expected

    def test_connector_states(self):
        from app.utils.enums import ConnectorState
        expected = {"DISCONNECTED", "CONNECTING", "CONNECTED",
                    "SUBSCRIBING", "ACTIVE", "WAIT_RETRY"}
        assert {s.value for s in ConnectorState} == expected

    def test_spread_types(self):
        from app.utils.enums import SpreadType
        expected = {"kimchi_premium", "same_currency"}
        assert {s.value for s in SpreadType} == expected

    def test_alert_directions(self):
        from app.utils.enums import AlertDirection
        expected = {"above", "below", "both"}
        assert {d.value for d in AlertDirection} == expected

    def test_alert_severities(self):
        from app.utils.enums import AlertSeverity
        expected = {"info", "warning", "critical"}
        assert {s.value for s in AlertSeverity} == expected

    def test_ws_event_types(self):
        from app.utils.enums import WsEventType
        expected = {
            "welcome", "snapshot", "price_update", "spread_update",
            "alert_triggered", "exchange_status", "heartbeat", "error",
            "subscribe", "subscribed", "unsubscribe", "unsubscribed", "pong",
        }
        assert {e.value for e in WsEventType} == expected

    def test_ws_channels(self):
        from app.utils.enums import WsChannel
        expected = {"prices", "spreads", "alerts", "exchange_status"}
        assert {c.value for c in WsChannel} == expected


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
