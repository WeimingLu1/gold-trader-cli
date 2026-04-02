"""Utility functions — time and availability time helpers."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time with timezone."""
    return datetime.now(timezone.utc)


def is_market_hours(dt: datetime | None = None) -> bool:
    """Check if given UTC time falls within main trading session (approx)."""
    dt = dt or utcnow()
    hour = dt.hour
    # Approximate: 07:00 UTC (Asia close) to 21:00 UTC (US close)
    return 7 <= hour < 21


def session_name(dt: datetime | None = None) -> str:
    """Return trading session name: asia / europe / us / closed."""
    dt = dt or utcnow()
    hour = dt.hour
    if 0 <= hour < 7:
        return "closed"  # weekend or pre-asia
    elif 7 <= hour < 12:
        return "asia"
    elif 12 <= hour < 17:
        return "europe"
    else:
        return "us"
