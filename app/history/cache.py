"""SQLite-backed historical data cache for backtesting."""
import sqlite3
from datetime import date, datetime, timedelta
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

CREATE TABLE IF NOT EXISTS news_headlines (
    date TEXT NOT NULL,       -- YYYY-MM-DD of the news date
    headline TEXT NOT NULL,
    source TEXT,
    url TEXT,
    fetched_at TEXT,
    PRIMARY KEY (date, headline)
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


# ── News headlines ──────────────────────────────────────────────────────────

def cache_headline(bar_date: date, headline: str, source: str | None, url: str | None) -> None:
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO news_headlines (date, headline, source, url, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bar_date.isoformat(), headline, source, url, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_headlines(bar_date: date) -> list[dict]:
    """Return all cached headlines for a given date."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT headline, source, url FROM news_headlines WHERE date = ?",
        (bar_date.isoformat(),)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def has_news_cache(start_date: date, end_date: date) -> bool:
    """Return True if we have headlines for most days in the range."""
    conn = _get_conn()
    count = conn.execute(
        "SELECT COUNT(DISTINCT date) FROM news_headlines WHERE date BETWEEN ? AND ?",
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchone()[0]
    conn.close()
    days = (end_date - start_date).days + 1
    # Consider cached if we have at least 50% of weekdays
    weekdays = sum(1 for i in range(days) if (start_date + timedelta(days=i)).weekday() < 5)
    return count >= weekdays * 0.5
