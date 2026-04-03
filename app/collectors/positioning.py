"""COT and positioning data collector — CFTC + Yahoo Finance fallback."""
import csv
import io
import httpx
import os
import json
import yfinance as yf
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData

# Cache file for last known COT positions
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".cot_cache.json")


def _load_cot_cache() -> dict:
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cot_cache(data: dict) -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


class PositioningCollector(BaseCollector):
    """
    Collects Commitment of Traders (COT) data for gold futures.

    Primary source: CFTC COT reports (disaggregated futures and options).
    CFTC URL: https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedFuturesandOptions/

    Fallback: Yahoo Finance GLD options data (estimated net positioning).
    When CFTC is accessible, uses real COT data. Otherwise falls back to
    yfinance-derived estimates based on GLD price momentum and volume divergence.

    COT data is published weekly (typically Tuesday for prior week's close).
    """

    name = "positioning"

    # CFTC historical data URL pattern (year/month based)
    # Format: disagg_com_git_YYYY_MM.csv
    COT_URL_TEMPLATE = (
        "https://www.cftc.gov/sites/default/files/foi/{year}_{month}/"
        "disagg_com_git_{year}_{month}.csv"
    )
    COT_URL_CURRENT = (
        "https://www.cftc.gov/sites/default/files/foi/disagg_com_git.csv"
    )

    async def collect(self) -> list[CollectedData]:
        now = datetime.now(timezone.utc)
        cache = _load_cot_cache()
        last_cot = cache.get("last_cot")

        # Try CFTC first
        data, source = await self._fetch_cftc(now)
        if data is None:
            # Fall back to yfinance-based estimate
            data = await self._estimate_from_yfinance()
            source = "yfinance_est" if data else "cot_mock"
            if data is None and last_cot:
                data = last_cot
                source = "cot_cached"

        if data is None:
            return self._mock_data(now)

        # Cache for next run
        _save_cot_cache({"last_cot": data})

        net_positions = data.get("net_positions", 0)
        long_short_ratio = data.get("long_short_ratio", 0.0)

        return [
            CollectedData(
                source=source,
                symbol="GOLD",
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload=data,
                normalized_payload={
                    "net_positions": net_positions,
                    "long_short_ratio": long_short_ratio,
                    "net_positions_change": data.get("net_change", 0),
                },
            )
        ]

    async def _fetch_cftc(self, now: datetime) -> tuple[dict | None, str]:
        """Try to fetch COT data from CFTC CSV."""
        year = now.strftime("%Y")
        month = now.strftime("%m")

        urls_to_try = [
            self.COT_URL_TEMPLATE.format(year=year, month=month),
            self.COT_URL_CURRENT,
        ]

        for url in urls_to_try:
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    r = await client.get(url)
                    if r.status_code != 200:
                        continue

                    text = r.text
                    reader = csv.DictReader(io.StringIO(text))
                    for row in reader:
                        exch = row.get("Market and Exchange Name", "")
                        if "Gold" not in exch:
                            continue

                        try:
                            noncomm_long = int(
                                row.get("Noncommercial Long", 0) or 0
                            )
                            noncomm_short = int(
                                row.get("Noncommercial Short", 0) or 0
                            )
                            noncomm_spread = int(
                                row.get("Noncommercial Spreading", 0) or 0
                            )
                            net = noncomm_long - noncomm_short - noncomm_spread
                            ratio = round(
                                noncomm_long / max(noncomm_short, 1), 2
                            )
                            return (
                                {
                                    "net_positions": net,
                                    "noncomm_long": noncomm_long,
                                    "noncomm_short": noncomm_short,
                                    "long_short_ratio": ratio,
                                },
                                "cftc",
                            )
                        except (ValueError, KeyError):
                            continue
            except Exception:
                continue

        return None, "cftc_failed"

    async def _estimate_from_yfinance(self) -> dict | None:
        """
        Estimate gold fund positioning from GLD price action.

        Uses momentum + volume divergence as a COT proxy:
        - Rising prices + rising volume → elevated net long conviction
        - Declining prices + falling volume → reduced net long conviction

        This is a rough proxy, not real COT data.
        In production, replace with actual broker/managed money data.
        """
        try:
            gld = yf.Ticker("GLD")
            hist = gld.history(period="3mo", interval="1wk")
            if hist is None or len(hist) < 5:
                return None

            closes = hist['Close'].values
            volumes = hist['Volume'].values
            n = len(closes)

            # Momentum: use all available data, capped at 20 periods
            lookback = min(n, 20)
            start_idx = n - lookback
            momentum = (closes[-1] - closes[start_idx]) / closes[start_idx] if closes[start_idx] > 0 else 0

            # Volume trend
            vol_lookback = min(n, 20)
            vol_start = n - vol_lookback
            avg_vol_recent = volumes[max(n-10, 0):].mean()
            avg_vol_all = volumes[vol_start:].mean()
            vol_trend = (avg_vol_recent - avg_vol_all) / max(avg_vol_all, 1)

            # Combine into a net conviction score
            score = momentum * 10 + vol_trend * 5

            # Map to COT-style contract range (-300k to +400k for gold)
            net_positions = int(score * 50_000)
            net_positions = max(-300_000, min(400_000, net_positions))

            # Long/short ratio estimate
            ratio = max(0.5, min(5.0, 2.0 + score * 5))

            return {
                "net_positions": net_positions,
                "long_short_ratio": round(ratio, 2),
                "net_change": 0,
            }
        except Exception:
            return None

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        """Fallback mock when all sources fail."""
        return [
            CollectedData(
                source="cot_mock",
                symbol="GOLD",
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={
                    "net_positions": 180_000,
                    "long_short_ratio": 2.3,
                },
                normalized_payload={
                    "net_positions": 180_000,
                    "long_short_ratio": 2.3,
                },
            )
        ]
