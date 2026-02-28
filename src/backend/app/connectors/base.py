"""Abstract base connector with 6-state FSM and exponential backoff.

Architecture reference: DD-3 (system-architecture.md §3)

State machine:
    DISCONNECTED → CONNECTING → CONNECTED → SUBSCRIBING → ACTIVE → WAIT_RETRY
                                                                  ↓
                                                            (backoff wait)
                                                                  ↓
                                                            CONNECTING (retry)

Backoff formula: min(BASE_DELAY * 2^attempt, MAX_DELAY)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

from app.utils.enums import ConnectorState
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

# Exponential backoff parameters
_BASE_DELAY_S: float = 1.0
_MAX_DELAY_S: float = 60.0
_MAX_RECONNECT_ATTEMPTS: int = 0  # 0 = unlimited


class BaseConnector(ABC):
    """Abstract WebSocket connector with 6-state FSM and exponential backoff.

    Subclasses must implement:
        - ws_url: str property
        - subscribe_message(): dict
        - normalize(raw_message: dict) -> TickerUpdate | None
    """

    def __init__(self, exchange_id: str, symbols: list[str]) -> None:
        self.exchange_id = exchange_id
        self.symbols = symbols

        self._state: ConnectorState = ConnectorState.DISCONNECTED
        self._reconnect_count: int = 0
        self._connected_since_ms: int | None = None
        self._last_message_ms: int | None = None
        self._latency_ms: int | None = None
        self._task: asyncio.Task | None = None

        # Callback set by ExchangeManager; called with each normalized TickerUpdate
        self._on_tick: "asyncio.Queue[TickerUpdate] | None" = None

        # When True, build_subscribe_message() returns a list that must be sent
        # as a single JSON array (e.g. Upbit/Bithumb protocol).
        # When False (default), each list element is sent as a separate message.
        self._subscribe_as_single_array: bool = False

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def state(self) -> ConnectorState:
        return self._state

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def connected_since_ms(self) -> int | None:
        return self._connected_since_ms

    @property
    def last_message_ms(self) -> int | None:
        return self._last_message_ms

    @property
    def latency_ms(self) -> int | None:
        return self._latency_ms

    @property
    def is_stale(self) -> bool:
        """True if no message received in the last 5 seconds."""
        from app.utils.enums import PRICE_STALE_THRESHOLD_MS
        if self._last_message_ms is None:
            return True
        return (int(time.time() * 1000) - self._last_message_ms) > PRICE_STALE_THRESHOLD_MS

    # ── Abstract interface ─────────────────────────────────────────────────────

    @property
    @abstractmethod
    def ws_url(self) -> str:
        """WebSocket endpoint URL for this exchange."""

    @abstractmethod
    def build_subscribe_message(self) -> list[dict] | dict:
        """Return the subscription payload to send after connection."""

    @abstractmethod
    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse an exchange-specific raw message into a canonical TickerUpdate.

        Returns None if the message should be ignored (e.g., heartbeat, ACK).
        """

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def attach_queue(self, queue: "asyncio.Queue[TickerUpdate]") -> None:
        """Attach the shared tick queue used by PriceStore."""
        self._on_tick = queue

    def start(self) -> asyncio.Task:
        """Spawn the connector's main loop as an asyncio Task."""
        self._task = asyncio.create_task(
            self._run_loop(), name=f"connector-{self.exchange_id}"
        )
        return self._task

    async def stop(self) -> None:
        """Cancel the connector task and transition to DISCONNECTED."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._transition(ConnectorState.DISCONNECTED)

    # ── Internal FSM ──────────────────────────────────────────────────────────

    def _transition(self, new_state: ConnectorState, reason: str | None = None) -> None:
        """Perform a state transition and log it."""
        old = self._state
        self._state = new_state
        logger.info(
            "[%s] %s → %s%s",
            self.exchange_id,
            old,
            new_state,
            f" ({reason})" if reason else "",
        )

    def _backoff_delay(self) -> float:
        """Calculate the current exponential backoff delay."""
        delay = min(_BASE_DELAY_S * (2 ** self._reconnect_count), _MAX_DELAY_S)
        return delay

    async def _run_loop(self) -> None:
        """Main reconnection loop. Runs until the task is cancelled."""
        import websockets

        while True:
            try:
                self._transition(ConnectorState.CONNECTING)
                t0 = time.monotonic()

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=30,
                    ping_timeout=20,
                    close_timeout=10,
                ) as ws:
                    self._transition(ConnectorState.CONNECTED)
                    self._connected_since_ms = int(time.time() * 1000)
                    self._latency_ms = int((time.monotonic() - t0) * 1000)

                    # Send subscription
                    self._transition(ConnectorState.SUBSCRIBING)
                    sub_msg = self.build_subscribe_message()
                    if self._subscribe_as_single_array and isinstance(sub_msg, list):
                        await ws.send(json.dumps(sub_msg))
                    elif isinstance(sub_msg, list):
                        for msg in sub_msg:
                            payload = json.dumps(msg) if not isinstance(msg, str) else msg
                            if payload and payload != "{}":
                                await ws.send(payload)
                    elif isinstance(sub_msg, dict) and sub_msg:
                        await ws.send(json.dumps(sub_msg))

                    self._transition(ConnectorState.ACTIVE)
                    self._reconnect_count = 0

                    async for raw_data in ws:
                        self._last_message_ms = int(time.time() * 1000)
                        try:
                            if isinstance(raw_data, bytes):
                                raw_data = raw_data.decode("utf-8")
                            raw = json.loads(raw_data)
                            tick = self.normalize(raw)
                            if tick is not None and self._on_tick is not None:
                                await self._on_tick.put(tick)
                        except Exception:
                            logger.exception("[%s] Failed to process message", self.exchange_id)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = self._backoff_delay()
                self._reconnect_count += 1
                self._transition(
                    ConnectorState.WAIT_RETRY,
                    reason=f"{type(exc).__name__}: {exc} — retry in {delay:.1f}s",
                )
                await asyncio.sleep(delay)
