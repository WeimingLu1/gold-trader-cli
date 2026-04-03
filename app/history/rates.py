"""Historical treasury yields and DXY from FRED via direct API."""
from datetime import date, datetime, timedelta
from io import BytesIO
import zipfile

import requests

from app.config import get_settings
from app.history import cache


class RatesHistoryStore:
    """
    Fetches and caches U.S. Treasury yields (DGS2/5/10/30) and DXY
    from FRED API directly (CSV endpoint, ZIP compressed).

    Uses a local SQLite cache to avoid repeated FRED API calls.
    """

    YIELD_SERIES = {
        "DGS2": "2-Year Treasury",
        "DGS5": "5-Year Treasury",
        "DGS10": "10-Year Treasury",
        "DGS30": "30-Year Treasury",
        "DTWEXBGS": "DXY Broad Index",
    }

    def get_bar(self, bar_date: date) -> dict | None:
        """
        Return {dgs2, dgs5, dgs10, dgs30, dxy} for a specific date.
        All values are in percent (not basis points).
        """
        cached = cache.get_rates_bar(bar_date)
        if cached:
            return {
                "dgs2": cached["dgs2"],
                "dgs5": cached["dgs5"],
                "dgs10": cached["dgs10"],
                "dgs30": cached["dgs30"],
                "dxy": cached["dtwexbs"],
            }
        return None

    def get_yields_and_dxy(
        self, bar_date: date
    ) -> dict[str, float] | None:
        """Return yields dict + DXY for a date."""
        return self.get_bar(bar_date)

    def get_dxy_change(self, bar_date: date) -> float | None:
        """Return DXY % change vs previous trading day."""
        today = self.get_bar(bar_date)
        if not today or today["dxy"] is None:
            return None

        # Find previous trading day (back up to 7 days)
        prev_date = bar_date - timedelta(days=1)
        for _ in range(7):
            prev = self.get_bar(prev_date)
            if prev and prev["dxy"] is not None:
                return (today["dxy"] - prev["dxy"]) / prev["dxy"] * 100
            prev_date -= timedelta(days=1)
        return None

    def _fetch_series_csv(
        self, series_id: str, start_date: date, end_date: date, api_key: str
    ) -> dict[date, float]:
        """Fetch a single FRED series as CSV and return {date: value}.

        FRED returns CSV data inside a ZIP archive.
        """
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=csv"
            f"&observation_start={start_date.strftime('%Y-%m-%d')}"
            f"&observation_end={end_date.strftime('%Y-%m-%d')}"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            print(f"[RatesHistory] FRED fetch failed for {series_id}: {e}")
            return {}

        # FRED returns ZIP — extract the CSV inside
        try:
            z = zipfile.ZipFile(BytesIO(resp.content))
            # FRED ZIP contains README.txt and obs._by_real-time_period.csv
            csv_name = next(
                (n for n in z.namelist() if n.startswith("obs")),
                z.namelist()[-1],  # fallback to last file
            )
            csv_text = z.read(csv_name).decode("utf-8")
        except Exception as e:
            print(f"[RatesHistory] Failed to unzip {series_id}: {e}")
            return {}

        result: dict[date, float] = {}
        lines = csv_text.strip().split("\n")
        # FRED format: period_start_date,DGS10,realtime_start_date,realtime_end_date
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 2:
                continue
            d_str, val = parts[0], parts[1]
            if val == ".":
                continue  # missing value
            try:
                d = date.fromisoformat(d_str)
                result[d] = float(val)
            except ValueError:
                continue
        return result

    def warm_cache(self, start_date: date, end_date: date) -> int:
        """
        Pre-fetch yields and DXY for the entire date range via FRED API.

        Returns number of unique dates cached.
        """
        settings = get_settings()
        fred_key = settings.fred_api_key

        if not fred_key or fred_key in ("", "your_fred_api_key_here"):
            print("[RatesHistory] No FRED API key configured.")
            return 0

        # Fetch all series
        all_series: dict[str, dict[date, float]] = {}
        for series_id in self.YIELD_SERIES:
            series_data = self._fetch_series_csv(series_id, start_date, end_date, fred_key)
            all_series[series_id] = series_data

        # Collect all unique dates across series
        all_dates = set()
        for series_data in all_series.values():
            all_dates.update(series_data.keys())

        inserted = 0
        for d in sorted(all_dates):
            cache.cache_rates_bar(
                bar_date=d,
                dgs2=all_series.get("DGS2", {}).get(d),
                dgs5=all_series.get("DGS5", {}).get(d),
                dgs10=all_series.get("DGS10", {}).get(d),
                dgs30=all_series.get("DGS30", {}).get(d),
                dxy=all_series.get("DTWEXBGS", {}).get(d),
            )
            inserted += 1
        return inserted
