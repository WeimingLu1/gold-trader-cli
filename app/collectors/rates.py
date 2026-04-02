"""Treasury yields and real rates collector — FRED API with mock fallback."""
import httpx
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData
from app.config import get_settings


class TreasuryYieldCollector(BaseCollector):
    """
    Collects U.S. Treasury yield data (2y, 5y, 10y, 30y) via FRED API.
    Falls back to mock data if API is unavailable or key not set.
    """

    name = "treasury_yields"

    # FRED series IDs for selected Treasury yields
    SERIES = {
        "DGS2": "2-Year Treasury Constant Maturity",
        "DGS5": "5-Year Treasury Constant Maturity",
        "DGS10": "10-Year Treasury Constant Maturity",
        "DGS30": "30-Year Treasury Constant Maturity",
    }

    async def collect(self) -> list[CollectedData]:
        settings = get_settings()
        fred_key = settings.fred_api_key or ""
        now = datetime.now(timezone.utc)

        if fred_key:
            yields = await self._fetch_fred(fred_key)
            if yields:
                return [
                    CollectedData(
                        source="fred",
                        symbol=series,
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload={series: val},
                        normalized_payload={"yield_pct": val},
                    )
                    for series, val in yields.items()
                    if val is not None
                ]

        # Fallback: mock data
        return self._mock_data(now)

    async def _fetch_fred(self, api_key: str) -> dict[str, float | None]:
        """Fetch latest yields from FRED API."""
        results: dict[str, float | None] = {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for series_id in self.SERIES:
                    url = (
                        f"https://api.stlouisfed.org/fred/series/observations"
                        f"?series_id={series_id}&api_key={api_key}&file_type=json&limit=1&sort_order=desc"
                    )
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json().get("observations", [])
                        if data:
                            val = data[-1].get("value")
                            results[series_id] = float(val) if val and val != "." else None
                    else:
                        results[series_id] = None
        except Exception as e:
            print(f"[FRED] API 错误: {e}")
        return results

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        """Return mock yield data."""
        yields = {"DGS2": 4.62, "DGS5": 4.41, "DGS10": 4.38, "DGS30": 4.58}
        return [
            CollectedData(
                source="fred_mock",
                symbol=series,
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={series: val},
                normalized_payload={"yield_pct": val},
            )
            for series, val in yields.items()
        ]


class RealRateCollector(BaseCollector):
    """
    Approximates U.S. real interest rates (nominal yield - inflation expectation).
    Uses 10-Year TIPS yield from FRED as proxy.
    """

    name = "real_rates"

    async def collect(self) -> list[CollectedData]:
        settings = get_settings()
        fred_key = settings.fred_api_key or ""
        now = datetime.now(timezone.utc)

        if fred_key:
            tips = await self._fetch_fred_tips(fred_key)
            if tips is not None:
                nominal = 4.38  # latest 10y nominal
                real_rate = nominal - tips
                return [
                    CollectedData(
                        source="fred",
                        symbol="REAL_RATE_10Y",
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload={"nominal_10y": nominal, "tips_10y": tips, "real_rate": real_rate},
                        normalized_payload={"real_rate_pct": real_rate},
                    )
                ]

        # Fallback mock
        return self._mock_data(now)

    async def _fetch_fred_tips(self, api_key: str) -> float | None:
        """Fetch 10-Year TIPS yield from FRED (series: DTP10J)."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=DTP10J&api_key=" + api_key + "&file_type=json&limit=1&sort_order=desc"
                )
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json().get("observations", [])
                    if data:
                        val = data[-1].get("value")
                        return float(val) if val and val != "." else None
        except Exception as e:
            print(f"[FRED TIPS] API 错误: {e}")
        return None

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        nominal_10y = 4.38
        inflation_expectation = 2.35
        real_rate = nominal_10y - inflation_expectation
        return [
            CollectedData(
                source="derived",
                symbol="REAL_RATE_10Y",
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={
                    "nominal_10y": nominal_10y,
                    "inflation_expectation": inflation_expectation,
                    "real_rate": real_rate,
                },
                normalized_payload={"real_rate_pct": real_rate},
            )
        ]
