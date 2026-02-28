"""AlertEngine — evaluates spread results against user-configured alert rules.

For each SpreadResult, checks all enabled AlertConfig rows. Fires
Telegram alerts and WebSocket notifications when thresholds are crossed,
respecting cooldown periods.

Architecture reference: DD-5 (3-tier alert severity mapping).
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal

from app.schemas.spread import SpreadResult
from app.utils.enums import AlertDirection, AlertSeverity, ALERT_SEVERITY_THRESHOLDS

logger = logging.getLogger(__name__)


def classify_severity(spread_pct: Decimal) -> AlertSeverity | None:
    """Classify a spread percentage into an alert severity tier.

    Returns None if the spread is below the INFO threshold (< 1.0%).

    Thresholds per DD-5:
        CRITICAL >= 3.0%
        WARNING  >= 2.0%
        INFO     >= 1.0%
    """
    abs_pct = abs(float(spread_pct))
    if abs_pct >= ALERT_SEVERITY_THRESHOLDS["critical"]:
        return AlertSeverity.CRITICAL
    if abs_pct >= ALERT_SEVERITY_THRESHOLDS["warning"]:
        return AlertSeverity.WARNING
    if abs_pct >= ALERT_SEVERITY_THRESHOLDS["info"]:
        return AlertSeverity.INFO
    return None


class AlertEngine:
    """Evaluates SpreadResult objects against AlertConfig rules.

    Responsibilities:
    - Load enabled AlertConfig rows from DB (cached, refreshed periodically)
    - For each SpreadResult, check direction + threshold + cooldown
    - On match: write AlertHistory, call TelegramBot, emit WS event
    """

    def __init__(self) -> None:
        # In-memory cooldown tracker: alert_config_id → last trigger time (unix ms)
        self._cooldowns: dict[int, int] = {}
        # Cached alert configs from DB
        self._configs: list[dict] = []
        self._configs_last_loaded: float = 0.0
        self._configs_ttl: float = 30.0  # Reload configs every 30 seconds
        # Telegram bot reference (set by main.py)
        self._telegram_bot: object | None = None
        # WS manager reference (set by main.py)
        self._ws_manager: object | None = None
        # Task
        self._task: asyncio.Task | None = None

    def set_telegram_bot(self, bot: object) -> None:
        """Set the TelegramBot instance for sending notifications."""
        self._telegram_bot = bot

    def set_ws_manager(self, manager: object) -> None:
        """Set the WS ConnectionManager for broadcasting alerts."""
        self._ws_manager = manager

    async def _load_configs(self) -> None:
        """Load enabled alert configurations from the database."""
        from app.database import async_session_factory  # noqa: PLC0415
        if async_session_factory is None:
            return

        now = time.monotonic()
        if now - self._configs_last_loaded < self._configs_ttl and self._configs:
            return  # Use cached configs

        try:
            from sqlalchemy import select  # noqa: PLC0415
            from app.models.alert import AlertConfig  # noqa: PLC0415

            async with async_session_factory() as session:
                stmt = select(AlertConfig).where(AlertConfig.enabled == 1)
                result = await session.execute(stmt)
                rows = result.scalars().all()
                self._configs = [
                    {
                        "id": row.id,
                        "chat_id": row.chat_id,
                        "symbol": row.symbol,
                        "exchange_a": row.exchange_a,
                        "exchange_b": row.exchange_b,
                        "threshold_pct": float(row.threshold_pct),
                        "direction": row.direction,
                        "cooldown_minutes": row.cooldown_minutes,
                    }
                    for row in rows
                ]
                self._configs_last_loaded = now
                logger.debug("AlertEngine: loaded %d active configs", len(self._configs))
        except Exception:
            logger.exception("AlertEngine: failed to load configs")

    async def evaluate(self, spread: SpreadResult) -> None:
        """Evaluate a spread result against all active alert configurations."""
        await self._load_configs()
        await self._evaluate_with_cached_configs(spread)

    async def _evaluate_with_cached_configs(self, spread: SpreadResult) -> None:
        """Evaluate a spread using already-loaded configs (no DB reload)."""
        severity = classify_severity(spread.spread_pct)

        for config in self._configs:
            if not self._matches(config, spread):
                continue

            # Check direction
            spread_val = float(spread.spread_pct)
            direction = config["direction"]
            threshold = config["threshold_pct"]

            if direction == AlertDirection.ABOVE and spread_val < threshold:
                continue
            elif direction == AlertDirection.BELOW and spread_val > -threshold:
                continue
            elif direction == AlertDirection.BOTH and abs(spread_val) < threshold:
                continue

            # Check cooldown
            if self._is_in_cooldown(config["id"], config["cooldown_minutes"]):
                continue

            # Trigger alert
            self._record_trigger(config["id"])

            # Determine severity for the message
            effective_severity = severity or AlertSeverity.INFO

            # Format message
            from app.services.telegram_bot import TelegramBot  # noqa: PLC0415
            message = TelegramBot.format_alert_message(
                symbol=spread.symbol,
                exchange_a=spread.exchange_a,
                exchange_b=spread.exchange_b,
                spread_pct=str(spread.spread_pct),
                severity=effective_severity.value,
                fx_rate=str(spread.fx_rate) if spread.fx_rate else None,
            )

            # Write alert history to DB
            telegram_msg_id = None
            telegram_delivered = False

            # Send Telegram notification
            if self._telegram_bot is not None:
                try:
                    telegram_msg_id = await self._telegram_bot.send_alert(
                        chat_id=config["chat_id"],
                        message=message,
                    )
                    telegram_delivered = telegram_msg_id is not None
                except Exception:
                    logger.exception("AlertEngine: Telegram send failed for config %d", config["id"])

            # Write history
            await self._write_history(
                config=config,
                spread=spread,
                message=message,
                severity=effective_severity,
                telegram_delivered=telegram_delivered,
                telegram_msg_id=telegram_msg_id,
            )

            # Broadcast via WebSocket
            if self._ws_manager is not None:
                try:
                    from app.utils.enums import WsChannel, WsEventType  # noqa: PLC0415
                    alert_ts = int(time.time() * 1000)
                    await self._ws_manager.broadcast(
                        {
                            "type": WsEventType.ALERT_TRIGGERED,
                            "data": {
                                "alert_config_id": config["id"],
                                "exchange_a": spread.exchange_a,
                                "exchange_b": spread.exchange_b,
                                "symbol": spread.symbol,
                                "spread_pct": str(spread.spread_pct),
                                "spread_type": spread.spread_type,
                                "threshold_pct": str(config["threshold_pct"]),
                                "direction": config["direction"],
                                "severity": effective_severity.value,
                                "fx_rate": str(spread.fx_rate) if spread.fx_rate else None,
                                "fx_source": spread.fx_source,
                                "telegram_delivered": telegram_delivered,
                                "timestamp_ms": alert_ts,
                            },
                            "timestamp_ms": alert_ts,
                        },
                        channel=WsChannel.ALERTS,
                    )
                except Exception:
                    logger.exception("AlertEngine: WS broadcast failed")

            logger.info(
                "AlertEngine: triggered alert config=%d %s %s-%s %s %.2f%%",
                config["id"],
                spread.symbol,
                spread.exchange_a,
                spread.exchange_b,
                spread.spread_type,
                spread.spread_pct,
            )

    async def evaluate_many(self, spreads: list[SpreadResult]) -> None:
        """Evaluate multiple spread results (used by SpreadCalculator callback)."""
        # Win 3: Load configs once per batch, not once per spread
        await self._load_configs()
        for spread in spreads:
            await self._evaluate_with_cached_configs(spread)

    def _matches(self, config: dict, spread: SpreadResult) -> bool:
        """Check if a spread result matches a config's symbol/exchange filters."""
        # Symbol filter
        if config["symbol"] is not None and config["symbol"] != spread.symbol:
            return False
        # Exchange pair filter
        if config["exchange_a"] is not None:
            if config["exchange_a"] != spread.exchange_a and config["exchange_a"] != spread.exchange_b:
                return False
        if config["exchange_b"] is not None:
            if config["exchange_b"] != spread.exchange_b and config["exchange_b"] != spread.exchange_a:
                return False
        return True

    def _is_in_cooldown(self, alert_config_id: int, cooldown_minutes: int) -> bool:
        """Return True if the alert is within its cooldown period."""
        last_trigger = self._cooldowns.get(alert_config_id)
        if last_trigger is None:
            return False
        elapsed_ms = int(time.time() * 1000) - last_trigger
        return elapsed_ms < (cooldown_minutes * 60 * 1000)

    def _record_trigger(self, alert_config_id: int) -> None:
        """Record the current time as the last trigger for this alert."""
        self._cooldowns[alert_config_id] = int(time.time() * 1000)

    async def _write_history(
        self,
        config: dict,
        spread: SpreadResult,
        message: str,
        severity: AlertSeverity,
        telegram_delivered: bool,
        telegram_msg_id: int | None,
    ) -> None:
        """Write an alert trigger event to the database."""
        from app.database import async_session_factory  # noqa: PLC0415
        if async_session_factory is None:
            return

        try:
            from app.models.alert import AlertConfig, AlertHistory  # noqa: PLC0415
            from sqlalchemy import update  # noqa: PLC0415

            async with async_session_factory() as session:
                async with session.begin():
                    history = AlertHistory(
                        alert_config_id=config["id"],
                        exchange_a=spread.exchange_a,
                        exchange_b=spread.exchange_b,
                        symbol=spread.symbol,
                        spread_pct=str(spread.spread_pct),
                        spread_type=spread.spread_type,
                        threshold_pct=str(config["threshold_pct"]),
                        direction=config["direction"],
                        price_a=str(spread.price_a),
                        price_b=str(spread.price_b),
                        fx_rate=str(spread.fx_rate) if spread.fx_rate else None,
                        fx_source=spread.fx_source,
                        message_text=message,
                        telegram_delivered=1 if telegram_delivered else 0,
                        telegram_message_id=telegram_msg_id,
                    )
                    session.add(history)

                    # Update trigger count and last_triggered_at
                    now_epoch = int(time.time())
                    await session.execute(
                        update(AlertConfig)
                        .where(AlertConfig.id == config["id"])
                        .values(
                            trigger_count=AlertConfig.trigger_count + 1,
                            last_triggered_at=now_epoch,
                            updated_at=now_epoch,
                        )
                    )
        except Exception:
            logger.exception("AlertEngine: failed to write history for config %d", config["id"])

    def invalidate_config_cache(self) -> None:
        """Force reload of alert configs on next evaluation."""
        self._configs_last_loaded = 0.0
