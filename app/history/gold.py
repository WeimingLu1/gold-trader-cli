"""Gold historical OHLCV data via yfinance (GC=F gold futures)."""
from datetime import date, datetime, timedelta
from typing import Literal
import yfinance as yf

from app.history import cache


class GoldHistoryStore:
    """
    Fetches and caches gold futures (GC=F) daily OHLCV via yfinance.

    On first access for a date range, fetches all bars and stores them
    in a local SQLite cache. Subsequent reads come from the cache.
    """

    TICKER = "GC=F"  # CME Gold Futures (front-month continuous)

    def get_bar(self, bar_date: date) -> dict | None:
        """
        Return OHLCV dict for a specific date, or None if not cached.

        Returns:
            {"open": float, "high": float, "low": float, "close": float, "volume": int}
        """
        cached = cache.get_gold_bar(bar_date)
        if cached:
            return {
                "open": cached["open"],
                "high": cached["high"],
                "low": cached["low"],
                "close": cached["close"],
                "volume": cached["volume"],
            }
        return None

    def get_close(self, bar_date: date) -> float | None:
        """Return close price for a date."""
        bar = self.get_bar(bar_date)
        return bar["close"] if bar else None

    def get_price_nearest(self, target_dt: datetime) -> float | None:
        """
        Return the close price closest to target_dt.

        If target_dt falls within a calendar day, return that day's close.
        If it's before market open (~09:30 ET), return previous day's close.
        """
        d = target_dt.date()
        bar = self.get_bar(d)
        if bar:
            return bar["close"]

        # Try previous day if we're near market open
        prev = d
        for _ in range(7):
            prev = prev - timedelta(days=1)
            bar = self.get_bar(prev)
            if bar:
                return bar["close"]
        return None

    def warm_cache(self, start_date: date, end_date: date) -> int:
        """
        Pre-fetch gold OHLCV for the entire date range and store in cache.

        Returns the number of bars fetched.
        """
        if cache.has_gold_cache(start_date, end_date):
            return -1  # already fully cached

        # yfinance expects datetime objects
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.min.time())

        try:
            df = yf.download(
                self.TICKER,
                start=start_dt,
                end=end_dt + timedelta(days=1),
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                return 0

            inserted = 0
            for idx, row in df.iterrows():
                d = idx.date() if hasattr(idx, "date") else idx.to_pydatetime().date()
                # Handle multi-level columns from yfinance (有时返回 pd.MultiIndex)
                def _scalar(val):
                    if hasattr(val, "item"):
                        return val.item()
                    return float(val)
                cache.cache_gold_bar(
                    bar_date=d,
                    open_=_scalar(row["Open"]),
                    high=_scalar(row["High"]),
                    low=_scalar(row["Low"]),
                    close=_scalar(row["Close"]),
                    volume=int(_scalar(row["Volume"])) if "Volume" in row else 0,
                )
                inserted += 1
            return inserted
        except Exception as e:
            print(f"[GoldHistory] warm_cache failed: {e}")
            return 0

    def get_ohlcv_series(
        self, start_date: date, end_date: date
    ) -> dict[date, dict]:
        """Return a dict of {date: OHLCV dict} for the range."""
        result: dict[date, dict] = {}
        cur = start_date
        while cur <= end_date:
            bar = self.get_bar(cur)
            if bar:
                result[cur] = bar
            cur += timedelta(days=1)
        return result
