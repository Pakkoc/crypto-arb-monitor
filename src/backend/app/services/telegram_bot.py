"""TelegramBot service — sends alert notifications via aiogram.

Architecture reference: DD-5 (Telegram alerting).
Uses aiogram 3.x with async Bot client.

Provides:
- Bot initialization and shutdown
- /start command (register chat_id)
- /status command (exchange connection status)
- Alert message formatting with severity icons
- send_alert() for AlertEngine integration
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.exchange_manager import ExchangeManager

logger = logging.getLogger(__name__)


class TelegramBot:
    """Sends formatted alert messages to Telegram chats.

    Integrates with aiogram 3.x for async Telegram API communication.
    Handles /start (chat registration) and /status (exchange status) commands.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._bot = None  # aiogram.Bot instance
        self._dp = None   # aiogram.Dispatcher instance
        self._exchange_manager: ExchangeManager | None = None
        self._polling_task = None

    def set_exchange_manager(self, manager: ExchangeManager) -> None:
        """Set the ExchangeManager reference for /status command."""
        self._exchange_manager = manager

    async def start(self) -> None:
        """Initialize the aiogram Bot and Dispatcher with command handlers."""
        if not self._token:
            logger.warning("TelegramBot: no token configured, bot disabled")
            return

        try:
            from aiogram import Bot, Dispatcher  # noqa: PLC0415
            from aiogram.filters import Command  # noqa: PLC0415
            from aiogram.types import Message  # noqa: PLC0415

            self._bot = Bot(token=self._token)
            self._dp = Dispatcher()

            # Register command handlers
            @self._dp.message(Command("start"))
            async def cmd_start(message: Message) -> None:
                """Handle /start — register chat ID for alerts."""
                chat_id = message.chat.id
                await message.answer(
                    f"Crypto Arbitrage Monitor\n\n"
                    f"Your chat ID: <code>{chat_id}</code>\n\n"
                    f"Use this ID when creating alerts via the dashboard.\n"
                    f"Commands:\n"
                    f"/start — Show this message\n"
                    f"/status — Exchange connection status",
                    parse_mode="HTML",
                )
                logger.info("TelegramBot: /start from chat_id=%d", chat_id)

            @self._dp.message(Command("status"))
            async def cmd_status(message: Message) -> None:
                """Handle /status — show exchange connection status."""
                if self._exchange_manager is None:
                    await message.answer("Exchange manager not available.")
                    return

                states = self._exchange_manager.get_connector_states()
                lines = ["<b>Exchange Status</b>\n"]
                for ex_id, info in states.items():
                    state = info.get("state", "UNKNOWN")
                    stale = info.get("is_stale", True)
                    # State emoji
                    emoji = "🟢" if state == "ACTIVE" and not stale else "🔴" if state in ("DISCONNECTED", "WAIT_RETRY") else "🟡"
                    name = info.get("name", ex_id)
                    lines.append(f"{emoji} <b>{name}</b>: {state}")
                    if info.get("latency_ms") is not None:
                        lines.append(f"   Latency: {info['latency_ms']}ms")
                    if info.get("reconnect_count", 0) > 0:
                        lines.append(f"   Reconnects: {info['reconnect_count']}")

                lines.append(f"\nConnected: {self._exchange_manager.get_connected_count()}/5")
                await message.answer("\n".join(lines), parse_mode="HTML")

            # Start polling in background (non-blocking)
            import asyncio  # noqa: PLC0415
            self._polling_task = asyncio.create_task(
                self._run_polling(), name="telegram-bot-polling"
            )

            logger.info("TelegramBot: initialized and polling started")
        except ImportError:
            logger.warning("TelegramBot: aiogram not installed, bot disabled")
        except Exception:
            logger.exception("TelegramBot: failed to initialize")

    async def _run_polling(self) -> None:
        """Run the dispatcher polling loop. Catches all exceptions to avoid crashes."""
        try:
            if self._dp and self._bot:
                await self._dp.start_polling(self._bot)
        except Exception:
            logger.exception("TelegramBot: polling error")

    async def stop(self) -> None:
        """Close the aiogram session and stop polling."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except Exception:
                pass

        if self._dp:
            await self._dp.stop_polling()

        if self._bot is not None:
            await self._bot.session.close()
            logger.info("TelegramBot: stopped")

    async def send_alert(
        self,
        chat_id: int,
        message: str,
        parse_mode: str = "HTML",
    ) -> int | None:
        """Send an alert message to a Telegram chat.

        Returns the Telegram message ID on success, None on failure.
        """
        if self._bot is None:
            logger.debug("TelegramBot: bot not initialized, skipping send")
            return None
        try:
            result = await self._bot.send_message(
                chat_id=chat_id, text=message, parse_mode=parse_mode
            )
            return result.message_id
        except Exception:
            logger.exception("TelegramBot: failed to send message to chat_id=%d", chat_id)
            return None

    @staticmethod
    def format_alert_message(
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        spread_pct: str,
        severity: str,
        fx_rate: str | None,
    ) -> str:
        """Format a human-readable Telegram alert message with severity icons.

        Severity icons:
            critical: 🚨
            warning:  ⚠️
            info:     ℹ️
        """
        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(severity, "📊")
        lines = [
            f"{emoji} <b>Arbitrage Alert — {severity.upper()}</b>",
            "",
            f"Symbol: <b>{symbol}</b>",
            f"Spread: <b>{spread_pct}%</b>",
            f"Pair: {exchange_a.capitalize()} ↔ {exchange_b.capitalize()}",
        ]
        if fx_rate:
            lines.append(f"FX Rate: {fx_rate} KRW/USDT")
        lines.extend([
            "",
            f"<i>Crypto Arbitrage Monitor</i>",
        ])
        return "\n".join(lines)
