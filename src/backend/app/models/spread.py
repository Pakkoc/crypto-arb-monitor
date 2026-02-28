"""SpreadRecord ORM model.

High-volume table: ~432,000 rows/day. Subject to 30-day retention cleanup.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SpreadRecord(Base):
    """A computed spread value between two exchanges for one symbol at a point in time."""

    __tablename__ = "spread_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_a: Mapped[str] = mapped_column(
        String, ForeignKey("exchanges.id"), nullable=False
    )
    exchange_b: Mapped[str] = mapped_column(
        String, ForeignKey("exchanges.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("tracked_symbols.symbol"), nullable=False
    )
    spread_pct: Mapped[str] = mapped_column(String, nullable=False)
    spread_type: Mapped[str] = mapped_column(String, nullable=False)  # kimchi_premium | same_currency
    price_a: Mapped[str] = mapped_column(String, nullable=False)
    price_b: Mapped[str] = mapped_column(String, nullable=False)
    is_stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    fx_rate: Mapped[str | None] = mapped_column(String, nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_spread_records_symbol_time", "symbol", "created_at"),
        Index("idx_spread_records_pair_symbol_time", "exchange_a", "exchange_b", "symbol", "created_at"),
        Index("idx_spread_records_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SpreadRecord id={self.id} {self.exchange_a}-{self.exchange_b} "
            f"{self.symbol!r} {self.spread_pct}% ({self.spread_type})>"
        )
