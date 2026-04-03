"""Treasury yields, real rates, and DXY collector — FRED API with mock fallback."""
import asyncio
import json
import os
import httpx
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData
from app.config import get_settings

# File to persist DXY previous value across runs
_DXY_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".dxy_state.json")


def _load_dxy_previous() -> float | None:
    """Load previous DXY value from state file."""
    try:
        if os.path.exists(_DXY_STATE_FILE):
            with open(_DXY_STATE_FILE) as f:
                data = json.load(f)
            return float(data.get("dxy", 0)) or None
    except Exception:
        pass
    return None


def _save_dxy_previous(dxy: float) -> None:
    """Save DXY value to state file for next run."""
    try:
        with open(_DXY_STATE_FILE, "w") as f:
            json.dump({"dxy": dxy}, f)
    except Exception:
        pass


class TreasuryYieldCollector(BaseCollector):
    """
    Collects U.S. Treasury yield data (2y, 5y, 10y, 30y) via FRED API.
    Falls back to mock data if API is unavailable or key not set.
    Each returned item includes the previous yield for computing changes.
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
            yields, yields_prev = await self._fetch_fred_with_history(fred_key)
            if yields:
                return [
                    CollectedData(
                        source="fred",
                        symbol=series,
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload={
                            series: val,
                            f"{series}_prev": yields_prev.get(series),
                        },
                        normalized_payload={
                            "yield_pct": val,
                            "yield_pct_prev": yields_prev.get(series),
                        },
                    )
                    for series, val in yields.items()
                    if val is not None
                ]

        # Fallback: mock data
        return self._mock_data(now)

    async def _fetch_fred_with_history(
        self, api_key: str
    ) -> tuple[dict[str, float | None], dict[str, float | None]]:
        """
        Fetch latest 2 observations per series from FRED.
        Returns (current_yields dict, previous_yields dict).
        """
        results: dict[str, float | None] = {}
        results_prev: dict[str, float | None] = {}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for series_id in self.SERIES:
                    url = (
                        f"https://api.stlouisfed.org/fred/series/observations"
                        f"?series_id={series_id}&api_key={api_key}&file_type=json&limit=2&sort_order=desc"
                    )
                    r = await client.get(url)
                    if r.status_code == 200:
                        data = r.json().get("observations", [])
                        if data:
                            # data[0] = most recent, data[1] = previous
                            cur = data[0].get("value")
                            prv = data[1].get("value") if len(data) > 1 else None
                            results[series_id] = float(cur) if cur and cur != "." else None
                            results_prev[series_id] = float(prv) if prv and prv != "." else None
                    else:
                        results[series_id] = None
                        results_prev[series_id] = None
        except Exception as e:
            print(f"[FRED] API 错误: {e}")
        return results, results_prev

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        """Return mock yield data with previous values set to None."""
        yields = {"DGS2": 4.62, "DGS5": 4.41, "DGS10": 4.38, "DGS30": 4.58}
        return [
            CollectedData(
                source="fred_mock",
                symbol=series,
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={series: val, f"{series}_prev": None},
                normalized_payload={"yield_pct": val, "yield_pct_prev": None},
            )
            for series, val in yields.items()
        ]


class DXYCollector(BaseCollector):
    """
    Collects U.S. Dollar Index (DXY) via FRED API (series: DTWEXBGS).
    Tracks previous value across runs to compute DXY change.
    Falls back to mock data if API is unavailable.
    """

    name = "dxy"
    FRED_SERIES = "DTWEXBGS"  # Trade Weighted USD Index (Broad)

    async def collect(self) -> list[CollectedData]:
        settings = get_settings()
        fred_key = settings.fred_api_key or ""
        now = datetime.now(timezone.utc)
        previous_dxy = _load_dxy_previous()

        if fred_key:
            current, previous = await self._fetch_fred_dxy(fred_key)
            if current is not None:
                # Save current as previous for next run
                _save_dxy_previous(current)
                prev_to_store = previous if previous is not None else previous_dxy
                return [
                    CollectedData(
                        source="fred",
                        symbol="DXY",
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload={"dxy": current, "dxy_prev": prev_to_store},
                        normalized_payload={"dxy": current, "dxy_prev": prev_to_store},
                    )
                ]

        # Fallback mock
        return self._mock_data(now, previous_dxy)

    async def _fetch_fred_dxy(
        self, api_key: str
    ) -> tuple[float | None, float | None]:
        """Fetch last 2 DXY observations from FRED."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={self.FRED_SERIES}&api_key={api_key}&file_type=json&limit=2&sort_order=desc"
                )
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json().get("observations", [])
                    if data:
                        cur = data[0].get("value")
                        prv = data[1].get("value") if len(data) > 1 else None
                        return (
                            float(cur) if cur and cur != "." else None,
                            float(prv) if prv and prv != "." else None,
                        )
        except Exception as e:
            print(f"[FRED DXY] API 错误: {e}")
        return None, None

    def _mock_data(self, now: datetime, previous: float | None) -> list[CollectedData]:
        current = 104.5
        return [
            CollectedData(
                source="mock",
                symbol="DXY",
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={"dxy": current, "dxy_prev": previous or 104.3},
                normalized_payload={"dxy": current, "dxy_prev": previous or 104.3},
            )
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
            tips, nominal_10y = await self._fetch_fred_tips_and_nominal(fred_key)
            if tips is not None and nominal_10y is not None:
                real_rate = nominal_10y - tips
                return [
                    CollectedData(
                        source="fred",
                        symbol="REAL_RATE_10Y",
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload={"nominal_10y": nominal_10y, "tips_10y": tips, "real_rate": real_rate},
                        normalized_payload={"real_rate_pct": real_rate},
                    )
                ]

        # Fallback mock
        return self._mock_data(now)

    async def _fetch_fred_tips_and_nominal(self, api_key: str) -> tuple[float | None, float | None]:
        """Fetch 10-Year TIPS yield and 10-Year nominal yield from FRED."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Fetch TIPS and 10y nominal in parallel
                tips_url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=DTP10J&api_key=" + api_key + "&file_type=json&limit=1&sort_order=desc"
                )
                nominal_url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=DGS10&api_key=" + api_key + "&file_type=json&limit=1&sort_order=desc"
                )
                tips_r, nominal_r = await asyncio.gather(
                    client.get(tips_url),
                    client.get(nominal_url),
                )

                tips_val = None
                if tips_r.status_code == 200:
                    data = tips_r.json().get("observations", [])
                    if data:
                        val = data[-1].get("value")
                        tips_val = float(val) if val and val != "." else None

                nominal_val = None
                if nominal_r.status_code == 200:
                    data = nominal_r.json().get("observations", [])
                    if data:
                        val = data[-1].get("value")
                        nominal_val = float(val) if val and val != "." else None

                return tips_val, nominal_val
        except Exception as e:
            print(f"[FRED TIPS] API 错误: {e}")
        return None, None

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
