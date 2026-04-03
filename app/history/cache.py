"""SQLite-backed historical data cache for backtesting."""
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path


# Default DB location: project root / history_cache.db
_CACHE_DB = Path(__file__).parent.parent.parent / "history_cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gold_bars (
    date TEXT PRIMARY KEY,   -- YYYY-MM-DD
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS rates_bars (
    date TEXT PRIMARY KEY,
    dgs2 REAL, dgs5 REAL, dgs10 REAL, dgs30 REAL,
    dtwexbs REAL,           -- DXY index value
    fetched_at TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.executescript(_SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Gold bars ────────────────────────────────────────────────────────────────

def cache_gold_bar(bar_date: date, open_, high, low, close, volume) -> None:
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO gold_bars (date, open, high, low, close, volume, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (bar_date.isoformat(), open_, high, low, close, volume, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_gold_bar(bar_date: date) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM gold_bars WHERE date = ?", (bar_date.isoformat(),)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def has_gold_cache(start_date: date, end_date: date) -> bool:
    conn = _get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM gold_bars WHERE date BETWEEN ? AND ?",
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchone()[0]
    conn.close()
    return count >= (end_date - start_date).days


# ── Rates / DXY bars ────────────────────────────────────────────────────────

def cache_rates_bar(bar_date: date, dgs2, dgs5, dgs10, dgs30, dxy) -> None:
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO rates_bars
        (date, dgs2, dgs5, dgs10, dgs30, dtwexbs, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (bar_date.isoformat(), dgs2, dgs5, dgs10, dgs30, dxy, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_rates_bar(bar_date: date) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM rates_bars WHERE date = ?", (bar_date.isoformat(),)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None
