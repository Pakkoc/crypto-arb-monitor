"""Alert ORM models: AlertConfig and AlertHistory."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertConfig(Base):
    """User-configured alert rule. Indefinite retention."""

    __tablename__ = "alert_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str | None] = mapped_column(
        String, ForeignKey("tracked_symbols.symbol"), nullable=True
    )
    exchange_a: Mapped[str | None] = mapped_column(
        String, ForeignKey("exchanges.id"), nullable=True
    )
    exchange_b: Mapped[str | None] = mapped_column(
        String, ForeignKey("exchanges.id"), nullable=True
    )
    threshold_pct: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # above | below | both
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_triggered_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_alert_configs_chat_id", "chat_id"),
        Index("idx_alert_configs_enabled", "enabled", sqlite_where=text("enabled = 1")),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertConfig id={self.id} chat_id={self.chat_id} "
            f"threshold={self.threshold_pct}% enabled={bool(self.enabled)}>"
        )


class AlertHistory(Base):
    """Immutable record of each alert trigger event. Indefinite retention."""

    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_configs.id"), nullable=False
    )
    exchange_a: Mapped[str] = mapped_column(String, nullable=False)
    exchange_b: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    spread_pct: Mapped[str] = mapped_column(String, nullable=False)
    spread_type: Mapped[str] = mapped_column(String, nullable=False)
    threshold_pct: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    price_a: Mapped[str] = mapped_column(String, nullable=False)
    price_b: Mapped[str] = mapped_column(String, nullable=False)
    fx_rate: Mapped[str | None] = mapped_column(String, nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String, nullable=True)
    message_text: Mapped[str] = mapped_column(String, nullable=False)
    telegram_delivered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_alert_history_config_time", "alert_config_id", "created_at"),
        Index("idx_alert_history_symbol_time", "symbol", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertHistory id={self.id} config={self.alert_config_id} "
            f"{self.exchange_a}-{self.exchange_b} {self.symbol!r} {self.spread_pct}%>"
        )
