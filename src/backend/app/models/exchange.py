"""Exchange ORM model.

Static reference table seeded on first run. Rows are never deleted.
"""
from __future__ import annotations

import time

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Exchange(Base):
    """Represents a supported cryptocurrency exchange."""

    __tablename__ = "exchanges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)  # KRW | USDT
    ws_url: Mapped[str] = mapped_column(String, nullable=False)
    rest_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("(unixepoch())")
    )

    def __repr__(self) -> str:
        return f"<Exchange id={self.id!r} name={self.name!r} state={'active' if self.is_active else 'inactive'}>"
