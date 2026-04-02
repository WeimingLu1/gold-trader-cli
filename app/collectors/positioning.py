"""COT and positioning data collector."""
from datetime import datetime, timezone
from app.collectors.base import BaseCollector, CollectedData


class PositioningCollector(BaseCollector):
    """
    Collects Commitment of Traders (COT) and positioning data.

    TODO: Integrate with:
      - CFTC COT reports (https://www.cftc.gov/MarketReports/CommitmentsofTraders/)
      - ISabelnet / OANDA positioning data
      - Broker sentiment data
    """

    name = "positioning"

    async def collect(self) -> list[CollectedData]:
        now = datetime.now(timezone.utc)

        # ── Mock data — replace with CFTC API ──────────────────────────────────────
        mock_data = {
            "net_noncommercial_positions": 180_000,  # contracts
            "net_commercial_positions": -200_000,
            "gold_etf_holdings_oz": 90_000_000,
            "funds_long_short_ratio": 2.3,
        }
        # ──────────────────────────────────────────────────────────────────────────

        return [
            CollectedData(
                source="cftc_mock",
                symbol="GOLD",
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload=mock_data,
                normalized_payload={
                    "net_positions": mock_data["net_noncommercial_positions"],
                    "etf_holdings_oz": mock_data["gold_etf_holdings_oz"],
                    "long_short_ratio": mock_data["funds_long_short_ratio"],
                },
            )
        ]
