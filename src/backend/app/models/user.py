"""Remaining ORM models: UserPreference, ExchangeStatusLog, FxRateHistory, TrackedSymbol."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrackedSymbol(Base):
    """Symbols currently being monitored across all exchanges."""

    __tablename__ = "tracked_symbols"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    def __repr__(self) -> str:
        return f"<TrackedSymbol {self.symbol!r} enabled={bool(self.enabled)}>"


class ExchangeStatusLog(Base):
    """Immutable log of exchange connector state transitions.

    Subject to 30-day retention cleanup.
    """

    __tablename__ = "exchange_status_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_exchange_status_log_exchange_time", "exchange_id", "created_at"),
        Index("idx_exchange_status_log_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExchangeStatusLog id={self.id} exchange={self.exchange_id!r} "
            f"{self.previous_state} → {self.state}>"
        )


class FxRateHistory(Base):
    """Historical FX (KRW/USD) rate observations.

    Deduplicated: only written when rate changes by >= 0.01 KRW.
    Subject to 30-day retention cleanup.
    """

    __tablename__ = "fx_rate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rate: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # upbit | exchangerate-api
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (Index("idx_fx_rate_history_time", "created_at"),)

    def __repr__(self) -> str:
        return f"<FxRateHistory id={self.id} rate={self.rate!r} source={self.source!r}>"


class UserPreference(Base):
    """Single-row table for dashboard and notification preferences.

    id is always 1 (enforced by CHECK constraint in the migration).
    """

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    preferences_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    def __repr__(self) -> str:
        return f"<UserPreference id={self.id} updated_at={self.updated_at}>"
