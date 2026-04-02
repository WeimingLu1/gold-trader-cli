"""Gold ETF flow data collector."""
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData


class ETFFlowCollector(BaseCollector):
    """
    Collects gold ETF holdings and flow data.

    TODO: Integrate with:
      - World Gold Council (holdings data)
      - ETF providers' daily disclosure (SPDR, iShares, etc.)
      - Bloomberg ETF data terminal
    """

    name = "etf_flows"

    async def collect(self) -> list[CollectedData]:
        now = datetime.now(timezone.utc)

        # ── Mock data — replace with real ETF API ──────────────────────────────────
        # SPDR Gold Trust (GLD) and iShares Gold Trust (IAU)
        mock_etfs = {
            "GLD": {"holdings_oz": 27_000_000, "flow_24h": -50_000},
            "IAU": {"holdings_oz": 15_000_000, "flow_24h": 30_000},
        }
        # ──────────────────────────────────────────────────────────────────────────

        items = []
        for ticker, data in mock_etfs.items():
            items.append(
                CollectedData(
                    source="etf_mock",
                    symbol=ticker,
                    event_time=now,
                    available_time=now,
                    fetched_at=now,
                    raw_payload={ticker: data},
                    normalized_payload={
                        "holdings_oz": data["holdings_oz"],
                        "flow_24h_oz": data["flow_24h"],
                        "flow_direction": "inflow" if data["flow_24h"] > 0 else "outflow",
                    },
                )
            )
        return items
