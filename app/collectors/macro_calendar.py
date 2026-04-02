"""Macro economic calendar collector."""
from datetime import datetime, timezone, timedelta
from app.collectors.base import BaseCollector, CollectedData


class MacroCalendarCollector(BaseCollector):
    """
    Collects upcoming macro economic events (FOMC, NFP, CPI, GDP, etc.).

    TODO: Integrate with:
      - forexfactory.com (scraping or API)
      - investing.com economic calendar
      - Bloomberg economic calendar
      - EIA weekly reports
    """

    name = "macro_calendar"

    HIGH_IMPACT_EVENTS = [
        "FOMC Meeting",
        "Fed Rate Decision",
        "Non-Farm Payrolls",
        "CPI",
        "PPI",
        "GDP",
        "ISM Manufacturing",
        "ISM Services",
        "Retail Sales",
        "PCE Inflation",
        "ECB Rate Decision",
        "BOJ Rate Decision",
    ]

    async def collect(self) -> list[CollectedData]:
        now = datetime.now(timezone.utc)

        # ── Mock data — replace with real calendar API ────────────────────────────
        mock_events = [
            {
                "event": "FOMC Meeting",
                "country": "US",
                "time_utc": now + timedelta(hours=6),
                "impact": "high",
            },
            {
                "event": "CPI",
                "country": "US",
                "time_utc": now + timedelta(days=1),
                "impact": "high",
            },
        ]
        # ──────────────────────────────────────────────────────────────────────────

        items = []
        for ev in mock_events:
            is_high_impact = ev["impact"] == "high"
            items.append(
                CollectedData(
                    source="macro_calendar",
                    symbol=ev["country"],
                    event_time=ev["time_utc"],
                    available_time=now,  # calendar is known ahead of time
                    fetched_at=now,
                    raw_payload=ev,
                    normalized_payload={
                        "event": ev["event"],
                        "impact": ev["impact"],
                        "is_high_impact": is_high_impact,
                        "hours_until_event": (ev["time_utc"] - now).total_seconds() / 3600,
                    },
                )
            )
        return items
