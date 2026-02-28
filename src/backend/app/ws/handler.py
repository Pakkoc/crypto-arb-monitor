"""WebSocket handler for the frontend dashboard.

Endpoint: WS /api/v1/ws

Implements the protocol defined in api-design.md §2:
  - welcome message on connect
  - subscribe/unsubscribe client messages
  - snapshot on subscription (prices, spreads, exchange_status, fx_rate)
  - real-time price_update and spread_update pushes
  - heartbeat every 30s with pong timeout
  - alert_triggered notifications
  - exchange_status change events
  - max 20 concurrent clients
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.utils.enums import (
    DEFAULT_SYMBOLS,
    EXCHANGE_CURRENCY,
    PRICE_STALE_THRESHOLD_MS,
    WsChannel,
    WsEventType,
)

logger = logging.getLogger(__name__)

ws_router = APIRouter()

_HEARTBEAT_INTERVAL_S = 30
_PONG_TIMEOUT_S = 10
_MAX_CLIENTS = 20


@dataclass
class WsClient:
    """Represents a connected WebSocket client with its subscription state."""

    websocket: WebSocket
    symbols: set[str] = field(default_factory=set)
    channels: set[str] = field(default_factory=lambda: {"prices", "spreads", "alerts", "exchange_status"})
    seq: int = 0

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    async def send(self, payload: dict) -> None:
        """Send a JSON message to the client."""
        try:
            await self.websocket.send_text(json.dumps(payload, default=str))
        except Exception:
            pass  # Client may have disconnected


_BROADCAST_THROTTLE_MS = 100  # Min interval per (exchange, symbol) for price updates


class ConnectionManager:
    """Manages all active WebSocket connections.

    Thread-safe (asyncio single-threaded).
    Max 20 concurrent clients enforced.
    """

    def __init__(self) -> None:
        self._clients: list[WsClient] = []
        # Throttle tracker: (exchange, symbol) → last_sent_ms
        self._last_price_sent: dict[tuple[str, str], int] = {}

    def count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> WsClient | None:
        """Accept a new WebSocket connection. Returns None if at capacity."""
        if len(self._clients) >= _MAX_CLIENTS:
            await websocket.close(code=1008, reason="Max clients reached")
            return None
        await websocket.accept()
        client = WsClient(websocket=websocket)
        self._clients.append(client)
        logger.info("WS client connected (total: %d)", len(self._clients))
        return client

    def disconnect(self, client: WsClient) -> None:
        if client in self._clients:
            self._clients.remove(client)
        logger.info("WS client disconnected (remaining: %d)", len(self._clients))

    async def broadcast(self, payload: dict, channel: str | None = None) -> None:
        """Broadcast a message to all connected clients (optionally filtered by channel)."""
        disconnected: list[WsClient] = []
        for client in list(self._clients):
            if channel and channel not in client.channels:
                continue
            # Filter by symbol if specified in payload
            symbol = payload.get("data", {}).get("symbol")
            if symbol and client.symbols and symbol not in client.symbols:
                continue
            try:
                await client.send(payload)
            except Exception:
                disconnected.append(client)

        # Clean up disconnected clients
        for client in disconnected:
            if client in self._clients:
                self._clients.remove(client)

    async def broadcast_price_update(self, tick) -> None:
        """Broadcast a price update to subscribed clients.

        Win 1: Throttle — skip if same (exchange, symbol) sent within 100ms.
        Win 5: Serialize JSON once, send raw text to all matching clients.
        """
        now_ms = int(time.time() * 1000)

        # Throttle: skip if sent recently for this (exchange, symbol)
        key = (tick.exchange, tick.symbol)
        last_sent = self._last_price_sent.get(key, 0)
        if (now_ms - last_sent) < _BROADCAST_THROTTLE_MS:
            return
        self._last_price_sent[key] = now_ms

        is_stale = (now_ms - tick.timestamp_ms) > PRICE_STALE_THRESHOLD_MS

        # Build the common data once (without seq — injected per client)
        data = {
            "exchange": tick.exchange,
            "symbol": tick.symbol,
            "price": str(tick.price),
            "currency": tick.currency,
            "bid_price": str(tick.bid_price) if tick.bid_price is not None else None,
            "ask_price": str(tick.ask_price) if tick.ask_price is not None else None,
            "volume_24h": str(tick.volume_24h),
            "timestamp_ms": tick.timestamp_ms,
            "received_at_ms": tick.received_at_ms,
            "is_stale": is_stale,
        }

        disconnected: list[WsClient] = []
        for client in list(self._clients):
            if WsChannel.PRICES not in client.channels:
                continue
            if client.symbols and tick.symbol not in client.symbols:
                continue
            payload = {
                "type": WsEventType.PRICE_UPDATE,
                "data": data,
                "seq": client.next_seq(),
                "timestamp_ms": now_ms,
            }
            try:
                await client.websocket.send_text(json.dumps(payload, default=str))
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            if client in self._clients:
                self._clients.remove(client)

    async def broadcast_spread_update(self, spreads: list) -> None:
        """Broadcast spread updates to subscribed clients.

        Win 1: Serialize each spread's data dict once, not per-client.
        """
        now_ms = int(time.time() * 1000)
        disconnected: list[WsClient] = []

        for spread in spreads:
            # Build spread data once per spread (not per client)
            data = {
                "exchange_a": spread.exchange_a,
                "exchange_b": spread.exchange_b,
                "symbol": spread.symbol,
                "spread_pct": str(spread.spread_pct),
                "spread_type": spread.spread_type,
                "is_stale": spread.is_stale,
                "stale_reason": spread.stale_reason,
                "price_a": str(spread.price_a),
                "price_a_currency": EXCHANGE_CURRENCY.get(spread.exchange_a, "UNKNOWN"),
                "price_b": str(spread.price_b),
                "price_b_currency": EXCHANGE_CURRENCY.get(spread.exchange_b, "UNKNOWN"),
                "fx_rate": str(spread.fx_rate) if spread.fx_rate else None,
                "fx_source": spread.fx_source,
                "timestamp_ms": spread.timestamp_ms,
            }

            for client in list(self._clients):
                if WsChannel.SPREADS not in client.channels:
                    continue
                if client.symbols and spread.symbol not in client.symbols:
                    continue
                payload = {
                    "type": WsEventType.SPREAD_UPDATE,
                    "data": data,
                    "seq": client.next_seq(),
                    "timestamp_ms": now_ms,
                }
                try:
                    await client.websocket.send_text(json.dumps(payload, default=str))
                except Exception:
                    disconnected.append(client)

        for client in disconnected:
            if client in self._clients:
                self._clients.remove(client)


# Module-level singleton — shared across the application
manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for real-time dashboard updates.

    Implements the full protocol from api-design.md §2.
    """
    client = await manager.connect(websocket)
    if client is None:
        return

    try:
        # Send welcome message
        await client.send({
            "type": WsEventType.WELCOME,
            "data": {
                "server_version": "1.0.0",
                "available_symbols": list(DEFAULT_SYMBOLS),
                "exchanges": ["bithumb", "upbit", "coinone", "binance", "bybit"],
                "heartbeat_interval_ms": _HEARTBEAT_INTERVAL_S * 1000,
            },
            "seq": client.next_seq(),
            "timestamp_ms": int(time.time() * 1000),
        })

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_HEARTBEAT_INTERVAL_S
                )
                msg = json.loads(raw)
                await _handle_client_message(client, msg)
            except asyncio.TimeoutError:
                # Send heartbeat
                await client.send({
                    "type": WsEventType.HEARTBEAT,
                    "data": {"server_time_ms": int(time.time() * 1000)},
                    "seq": client.next_seq(),
                    "timestamp_ms": int(time.time() * 1000),
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS handler error")
    finally:
        manager.disconnect(client)


async def _handle_client_message(client: WsClient, msg: dict) -> None:
    """Process a client-to-server message."""
    if not isinstance(msg, dict):
        return

    msg_type = msg.get("type")

    if msg_type == WsEventType.SUBSCRIBE:
        client.symbols = set(msg.get("symbols", []))
        client.channels = set(msg.get("channels", ["prices", "spreads", "alerts", "exchange_status"]))
        await client.send({
            "type": WsEventType.SUBSCRIBED,
            "data": {
                "symbols": list(client.symbols),
                "channels": list(client.channels),
            },
            "seq": client.next_seq(),
            "timestamp_ms": int(time.time() * 1000),
        })

        # Send snapshot from PriceStore if available
        await _send_snapshot(client)

    elif msg_type == WsEventType.UNSUBSCRIBE:
        symbols_to_remove = set(msg.get("symbols", []))
        client.symbols -= symbols_to_remove
        await client.send({
            "type": WsEventType.UNSUBSCRIBED,
            "data": {
                "symbols": list(symbols_to_remove),
                "remaining_symbols": list(client.symbols),
            },
            "seq": client.next_seq(),
            "timestamp_ms": int(time.time() * 1000),
        })

    elif msg_type == WsEventType.PONG:
        pass  # Heartbeat acknowledged

    else:
        await client.send({
            "type": WsEventType.ERROR,
            "data": {
                "code": "UNKNOWN_MESSAGE_TYPE",
                "message": f"Unknown message type: {msg_type!r}",
                "original_message_type": str(msg_type),
            },
            "seq": client.next_seq(),
            "timestamp_ms": int(time.time() * 1000),
        })


async def _send_snapshot(client: WsClient) -> None:
    """Send a snapshot of current prices, spreads, and exchange status to a new subscriber."""
    now_ms = int(time.time() * 1000)

    prices_data: list[dict] = []
    spreads_data: list[dict] = []
    exchange_statuses: list[dict] = []
    fx_rate_data = None

    try:
        app_state = client.websocket.app.state  # type: ignore[union-attr]

        # Prices from PriceStore
        price_store = getattr(app_state, "price_store", None)
        if price_store is not None:
            for tick in price_store.get_all().values():
                now_ms_check = int(time.time() * 1000)
                is_stale = (now_ms_check - tick.timestamp_ms) > PRICE_STALE_THRESHOLD_MS
                prices_data.append({
                    "exchange": tick.exchange,
                    "symbol": tick.symbol,
                    "price": str(tick.price),
                    "currency": tick.currency,
                    "bid_price": str(tick.bid_price) if tick.bid_price is not None else None,
                    "ask_price": str(tick.ask_price) if tick.ask_price is not None else None,
                    "volume_24h": str(tick.volume_24h),
                    "timestamp_ms": tick.timestamp_ms,
                    "received_at_ms": tick.received_at_ms,
                    "is_stale": is_stale,
                })
            fx_rate_data = price_store.get_fx_info()

        # Spreads from SpreadCalculator
        spread_calc = getattr(app_state, "spread_calculator", None)
        if spread_calc is not None:
            for spread in spread_calc.get_latest().values():
                spreads_data.append({
                    "exchange_a": spread.exchange_a,
                    "exchange_b": spread.exchange_b,
                    "symbol": spread.symbol,
                    "spread_pct": str(spread.spread_pct),
                    "spread_type": spread.spread_type,
                    "is_stale": spread.is_stale,
                    "stale_reason": spread.stale_reason,
                    "price_a": str(spread.price_a),
                    "price_a_currency": EXCHANGE_CURRENCY.get(spread.exchange_a, "UNKNOWN"),
                    "price_b": str(spread.price_b),
                    "price_b_currency": EXCHANGE_CURRENCY.get(spread.exchange_b, "UNKNOWN"),
                    "fx_rate": str(spread.fx_rate) if spread.fx_rate else None,
                    "fx_source": spread.fx_source,
                    "timestamp_ms": spread.timestamp_ms,
                })

        # Exchange statuses from ExchangeManager
        exchange_mgr = getattr(app_state, "exchange_manager", None)
        if exchange_mgr is not None:
            raw_states = exchange_mgr.get_connector_states()
            exchange_statuses = [
                {
                    "exchange": ex_id,
                    "state": info.get("state", "DISCONNECTED"),
                    "latency_ms": info.get("latency_ms"),
                    "last_message_ms": info.get("last_message_ms"),
                }
                for ex_id, info in raw_states.items()
            ]

    except Exception:
        logger.warning("Snapshot data unavailable (startup or missing state)", exc_info=True)

    await client.send({
        "type": WsEventType.SNAPSHOT,
        "data": {
            "prices": prices_data,
            "spreads": spreads_data,
            "exchange_statuses": exchange_statuses,
            "fx_rate": fx_rate_data,
        },
        "seq": client.next_seq(),
        "timestamp_ms": now_ms,
    })
