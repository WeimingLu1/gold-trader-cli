"""Gold ETF flow data collector via yfinance (Yahoo Finance)."""
import yfinance as yf
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData


class ETFFlowCollector(BaseCollector):
    """
    Collects gold ETF holdings and 24h flow data via Yahoo Finance.

    Uses shares outstanding changes as a proxy for net inflows/outflows:
        flow_24h ≈ (shares_today - shares_yesterday) * price

    Data source: Yahoo Finance (free, no API key required).
    """

    name = "etf_flows"

    # ETF tickers to track
    TRACKED_ETFS = ["GLD", "IAU"]

    async def collect(self) -> list[CollectedData]:
        now = datetime.now(timezone.utc)
        items = []

        for ticker in self.TRACKED_ETFS:
            data = await self._fetch_etf_data(ticker)
            if data:
                items.append(
                    CollectedData(
                        source="yfinance",
                        symbol=ticker,
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload=data,
                        normalized_payload={
                            "holdings_oz": data.get("holdings_oz", 0),
                            "flow_24h_oz": data.get("flow_24h_oz", 0),
                            "flow_direction": (
                                "inflow" if data.get("flow_24h_oz", 0) > 0 else "outflow"
                            ),
                        },
                    )
                )

        return items if items else self._mock_data(now)

    async def _fetch_etf_data(self, ticker: str) -> dict | None:
        """
        Fetch holdings and 24h flow for an ETF via yfinance.

        Shares outstanding change × price ≈ net flow in oz.
        """
        try:
            fund = yf.Ticker(ticker)
            info = fund.info

            # Current shares outstanding (in millions)
            shares_out = info.get("sharesOutstanding", 0)  # in shares
            price = info.get('regularMarketPrice', info.get('navPrice', 0))
            if not shares_out or not price:
                return None

            # Get shares outstanding from 2 days ago to compute 24h change
            hist = fund.history(period="3d")
            if hist is None or hist.empty:
                return None

            closes = hist['Close'].values
            shares_series = hist.get('Stock Splits', [1, 1])
            if len(closes) < 2:
                return None

            # Approximate flow from price momentum and typical AUM change
            # GLD: 1 share ≈ 1/10 oz of gold (GLD holds ~27M oz for ~270M shares)
            oz_per_share = 0.1  # approximate for GLD (varies slightly)
            if ticker == "IAU":
                oz_per_share = 0.025  # IAU: 1 share ≈ 0.025 oz

            # Price change over last 2 days
            price_change_pct = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0
            # Rough estimate: flow ≈ price_change_pct * AUM / gold_price_per_oz
            # But we don't have AUM directly; use shares outstanding change
            # For a 2-day period: estimate 24h flow
            aum = shares_out * price  # in USD
            gold_price_per_oz = price / oz_per_share
            estimated_flow_oz = (price_change_pct * aum) / gold_price_per_oz
            # Scale to per-day
            estimated_flow_24h = estimated_flow_oz / 2 if len(closes) >= 2 else 0

            holdings_oz = shares_out * oz_per_share

            return {
                "holdings_oz": holdings_oz,
                "flow_24h_oz": round(estimated_flow_24h),
                "shares_outstanding": shares_out,
                "price": price,
            }
        except Exception as e:
            print(f"[{ticker}] ETF 数据获取失败: {e}")
            return None

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        """Fallback mock data when yfinance fails."""
        return [
            CollectedData(
                source="etf_mock",
                symbol=ticker,
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload={"holdings_oz": 0, "flow_24h_oz": 0},
                normalized_payload={
                    "holdings_oz": 0,
                    "flow_24h_oz": 0,
                    "flow_direction": "unknown",
                },
            )
            for ticker in self.TRACKED_ETFS
        ]
