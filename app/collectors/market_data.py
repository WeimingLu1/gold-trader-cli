"""XAUUSD market data collector — supports GoldAPI.io and mock fallback."""
import random
import httpx
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData
from app.config import get_settings


class XAUUSDCollector(BaseCollector):
    """
    Collects current XAUUSD price via GoldAPI.io.
    Falls back to mock data if API is unavailable or key not set.
    """

    name = "xauusd"
    API_URL = "https://www.goldapi.io/api/XAU/USD"

    async def collect(self) -> list[CollectedData]:
        data = await self._fetch_live()
        return [data]

    async def _fetch_live(self) -> CollectedData:
        """Fetch live XAUUSD from GoldAPI.io, with mock fallback."""
        settings = get_settings()
        gold_key = settings.gold_api_key or ""

        now = datetime.now(timezone.utc)

        # ── Try GoldAPI.io ───────────────────────────────────────────────────────
        if gold_key and gold_key not in ("", "your_gold_api_key_here"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        self.API_URL,
                        headers={"x-access-token": gold_key, "Content-Type": "application/json"},
                    )
                    if response.status_code == 200:
                        json = response.json()
                        price = float(json.get("price", 0))
                        bid = float(json.get("bid", price))
                        ask = float(json.get("ask", price))
                        spread = round(ask - bid, 2)
                        return CollectedData(
                            source="goldapi.io",
                            symbol="XAUUSD",
                            event_time=now,
                            available_time=now,
                            fetched_at=now,
                            raw_payload=json,
                            normalized_payload={
                                "price": price,
                                "bid": bid,
                                "ask": ask,
                                "spread": spread,
                                "mid": round((bid + ask) / 2, 2),
                            },
                        )
                    else:
                        print(f"[goldapi.io] 请求失败: {response.status_code} {response.text[:100]}")
            except Exception as e:
                print(f"[goldapi.io] 连接错误: {e}")

        # ── Mock fallback ────────────────────────────────────────────────────────
        base_price = 2345.50
        spread = 0.40
        bid = base_price - spread / 2
        ask = base_price + spread / 2
        price = round(bid + random.uniform(0, spread), 2)

        return CollectedData(
            source="mock",
            symbol="XAUUSD",
            event_time=now,
            available_time=now,
            fetched_at=now,
            raw_payload={"price": price, "bid": bid, "ask": ask},
            normalized_payload={
                "price": price,
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "mid": round((bid + ask) / 2, 2),
            },
        )


class HistoricalPriceStore:
    """
    Simple in-memory store of recent price history.
    """

    def __init__(self, max_points: int = 100):
        self._prices: dict[datetime, float] = {}
        self._max_points = max_points

    def add(self, dt: datetime, price: float) -> None:
        self._prices[dt] = price
        if len(self._prices) > self._max_points:
            oldest = min(self._prices)
            del self._prices[oldest]

    def get_history(self) -> dict[datetime, float]:
        return dict(self._prices)
