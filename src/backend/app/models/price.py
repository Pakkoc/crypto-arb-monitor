"""PriceSnapshot ORM model.

High-volume table: ~216,000 rows/day. Subject to 30-day retention cleanup.
Prices are stored as TEXT (Decimal-as-string) to preserve exact precision.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PriceSnapshot(Base):
    """A single normalized price observation from one exchange for one symbol."""

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[str] = mapped_column(
        String, ForeignKey("exchanges.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("tracked_symbols.symbol"), nullable=False
    )
    price: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    bid_price: Mapped[str | None] = mapped_column(String, nullable=True)
    ask_price: Mapped[str | None] = mapped_column(String, nullable=True)
    volume_24h: Mapped[str] = mapped_column(String, nullable=False)
    exchange_timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    __table_args__ = (
        Index("idx_price_snapshots_symbol_time", "symbol", "created_at"),
        Index("idx_price_snapshots_exchange_symbol_time", "exchange_id", "symbol", "created_at"),
        Index("idx_price_snapshots_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceSnapshot id={self.id} exchange={self.exchange_id!r} "
            f"symbol={self.symbol!r} price={self.price!r}>"
        )
