"""Initial schema: all 9 tables with indexes and seed data.

Revision ID: 001_initial_schema
Revises: (none — first migration)
Create Date: 2026-02-28

Tables:
  1. exchanges            — static reference, 5 rows seeded
  2. tracked_symbols      — 5 default symbols seeded
  3. price_snapshots      — high-volume, 3 indexes, 30-day retention
  4. spread_records       — high-volume, 3 indexes, 30-day retention
  5. alert_configs        — user-managed, 2 indexes, includes last_triggered_at + trigger_count
  6. alert_history        — indefinite retention, 2 indexes
  7. exchange_status_log  — 2 indexes, 30-day retention
  8. fx_rate_history      — 1 index, 30-day retention
  9. user_preferences     — single row, seeded with defaults
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── 1. exchanges ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE exchanges (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            currency    TEXT NOT NULL CHECK (currency IN ('KRW', 'USDT')),
            ws_url      TEXT NOT NULL,
            rest_url    TEXT,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        INSERT INTO exchanges VALUES
            ('bithumb',  'Bithumb',  'KRW',  'wss://ws-api.bithumb.com/websocket/v1',   'https://api.bithumb.com',    1, unixepoch()),
            ('upbit',    'Upbit',    'KRW',  'wss://api.upbit.com/websocket/v1',         'https://api.upbit.com',      1, unixepoch()),
            ('coinone',  'Coinone',  'KRW',  'wss://stream.coinone.co.kr',               'https://api.coinone.co.kr',  1, unixepoch()),
            ('binance',  'Binance',  'USDT', 'wss://stream.binance.com:9443/ws',         'https://api.binance.com',    1, unixepoch()),
            ('bybit',    'Bybit',    'USDT', 'wss://stream.bybit.com/v5/public/spot',    'https://api.bybit.com',      1, unixepoch())
    """)

    # ── 2. tracked_symbols ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE tracked_symbols (
            symbol      TEXT PRIMARY KEY,
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
            updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        INSERT INTO tracked_symbols (symbol) VALUES
            ('BTC'), ('ETH'), ('XRP'), ('SOL'), ('DOGE')
    """)

    # ── 3. price_snapshots ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE price_snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange_id             TEXT NOT NULL REFERENCES exchanges(id),
            symbol                  TEXT NOT NULL REFERENCES tracked_symbols(symbol),
            price                   TEXT NOT NULL,
            currency                TEXT NOT NULL,
            bid_price               TEXT,
            ask_price               TEXT,
            volume_24h              TEXT NOT NULL,
            exchange_timestamp_ms   INTEGER NOT NULL,
            received_at_ms          INTEGER NOT NULL,
            created_at              INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_price_snapshots_symbol_time
            ON price_snapshots (symbol, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_price_snapshots_exchange_symbol_time
            ON price_snapshots (exchange_id, symbol, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_price_snapshots_created_at
            ON price_snapshots (created_at)
    """)

    # ── 4. spread_records ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE spread_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange_a      TEXT NOT NULL REFERENCES exchanges(id),
            exchange_b      TEXT NOT NULL REFERENCES exchanges(id),
            symbol          TEXT NOT NULL REFERENCES tracked_symbols(symbol),
            spread_pct      TEXT NOT NULL,
            spread_type     TEXT NOT NULL CHECK (spread_type IN ('kimchi_premium', 'same_currency')),
            price_a         TEXT NOT NULL,
            price_b         TEXT NOT NULL,
            is_stale        INTEGER NOT NULL DEFAULT 0,
            stale_reason    TEXT,
            fx_rate         TEXT,
            fx_source       TEXT,
            timestamp_ms    INTEGER NOT NULL,
            created_at      INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_spread_records_symbol_time
            ON spread_records (symbol, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_spread_records_pair_symbol_time
            ON spread_records (exchange_a, exchange_b, symbol, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_spread_records_created_at
            ON spread_records (created_at)
    """)

    # ── 5. alert_configs ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE alert_configs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id             INTEGER NOT NULL,
            symbol              TEXT REFERENCES tracked_symbols(symbol),
            exchange_a          TEXT REFERENCES exchanges(id),
            exchange_b          TEXT REFERENCES exchanges(id),
            threshold_pct       TEXT NOT NULL,
            direction           TEXT NOT NULL CHECK (direction IN ('above', 'below', 'both')),
            cooldown_minutes    INTEGER NOT NULL DEFAULT 5 CHECK (cooldown_minutes BETWEEN 1 AND 60),
            enabled             INTEGER NOT NULL DEFAULT 1,
            last_triggered_at   INTEGER,
            trigger_count       INTEGER NOT NULL DEFAULT 0,
            created_at          INTEGER NOT NULL DEFAULT (unixepoch()),
            updated_at          INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_alert_configs_chat_id
            ON alert_configs (chat_id)
    """)
    op.execute("""
        CREATE INDEX idx_alert_configs_enabled
            ON alert_configs (enabled) WHERE enabled = 1
    """)

    # ── 6. alert_history ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE alert_history (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_config_id      INTEGER NOT NULL REFERENCES alert_configs(id),
            exchange_a           TEXT NOT NULL,
            exchange_b           TEXT NOT NULL,
            symbol               TEXT NOT NULL,
            spread_pct           TEXT NOT NULL,
            spread_type          TEXT NOT NULL,
            threshold_pct        TEXT NOT NULL,
            direction            TEXT NOT NULL,
            price_a              TEXT NOT NULL,
            price_b              TEXT NOT NULL,
            fx_rate              TEXT,
            fx_source            TEXT,
            message_text         TEXT NOT NULL,
            telegram_delivered   INTEGER NOT NULL DEFAULT 0,
            telegram_message_id  INTEGER,
            created_at           INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_alert_history_config_time
            ON alert_history (alert_config_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_alert_history_symbol_time
            ON alert_history (symbol, created_at DESC)
    """)

    # ── 7. exchange_status_log ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE exchange_status_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange_id     TEXT NOT NULL REFERENCES exchanges(id),
            state           TEXT NOT NULL,
            previous_state  TEXT,
            latency_ms      INTEGER,
            reason          TEXT,
            created_at      INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_exchange_status_log_exchange_time
            ON exchange_status_log (exchange_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_exchange_status_log_created_at
            ON exchange_status_log (created_at)
    """)

    # ── 8. fx_rate_history ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE fx_rate_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            rate            TEXT NOT NULL,
            source          TEXT NOT NULL CHECK (source IN ('upbit', 'exchangerate-api')),
            timestamp_ms    INTEGER NOT NULL,
            created_at      INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute("""
        CREATE INDEX idx_fx_rate_history_time
            ON fx_rate_history (created_at DESC)
    """)

    # ── 9. user_preferences ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE user_preferences (
            id                  INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            preferences_json    TEXT NOT NULL DEFAULT '{}',
            updated_at          INTEGER NOT NULL DEFAULT (unixepoch())
        )
    """)
    op.execute(r"""
        INSERT INTO user_preferences (preferences_json) VALUES (
            '{"dashboard":{"default_symbol":"BTC","visible_exchanges":["bithumb","upbit","coinone","binance","bybit"],"spread_matrix_mode":"percentage","chart_interval":"5m","theme":"dark"},"notifications":{"telegram_enabled":true,"telegram_chat_id":null,"sound_enabled":true},"timezone":"Asia/Seoul","locale":"ko-KR"}'
        )
    """)


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.execute("DROP TABLE IF EXISTS user_preferences")
    op.execute("DROP TABLE IF EXISTS fx_rate_history")
    op.execute("DROP TABLE IF EXISTS exchange_status_log")
    op.execute("DROP TABLE IF EXISTS alert_history")
    op.execute("DROP TABLE IF EXISTS alert_configs")
    op.execute("DROP TABLE IF EXISTS spread_records")
    op.execute("DROP TABLE IF EXISTS price_snapshots")
    op.execute("DROP TABLE IF EXISTS tracked_symbols")
    op.execute("DROP TABLE IF EXISTS exchanges")
