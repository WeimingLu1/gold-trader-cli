"""Regime detection features — risk state, volatility regime, event windows."""
from app.features.base import FeatureSnapshot
from app.collectors.base import CollectedData


def build_regime_features(
    volatility_24h: float,
    macro_events: list[CollectedData],
    risk_assets: list[CollectedData] | None = None,  # e.g. VIX, SPY
) -> dict:
    """
    Classify market regime based on volatility, macro calendar, and risk assets.

    Args:
        volatility_24h: 24h annualized volatility from market_features.
        macro_events: Upcoming macro events from MacroCalendarCollector.
        risk_assets: Optional price/change data for risk-asset proxies (e.g. VIX).

    Returns:
        Dict of regime feature fields compatible with FeatureSnapshot.
    """

    # ── Volatility regime ────────────────────────────────────────────────────
    if volatility_24h > 0.20:   # >20% annualized vol = high
        vol_regime = "high"
    elif volatility_24h < 0.08:  # <8% = low
        vol_regime = "low"
    else:
        vol_regime = "normal"

    # ── Event window ─────────────────────────────────────────────────────────
    # Only flag as event window if high-impact event within 4 hours
    min_hours = float("inf")
    has_high_impact = False
    for ev in macro_events:
        if ev.normalized_payload and ev.normalized_payload.get("is_high_impact", False):
            has_high_impact = True
            hours = ev.normalized_payload.get("hours_until_event", 999)
            min_hours = min(min_hours, hours)

    hours_until_event = min_hours if has_high_impact else None
    event_window = has_high_impact and (hours_until_event is not None and hours_until_event <= 4)

    # ── Risk state ───────────────────────────────────────────────────────────
    # Use VIX from risk_assets if available
    # VIX > 20 → risk-off (flight to safety → bullish gold)
    # VIX < 15 → risk-on
    # Otherwise → neutral
    risk_state = "neutral"
    if risk_assets:
        for asset in risk_assets:
            if asset.symbol and "VIX" in asset.symbol.upper():
                vix_val = None
                if asset.normalized_payload:
                    vix_val = asset.normalized_payload.get("price") or asset.normalized_payload.get("value")
                elif asset.raw_payload:
                    vix_val = asset.raw_payload.get("VIX") or asset.raw_payload.get("price")
                if vix_val is not None:
                    try:
                        vix = float(vix_val)
                        if vix > 20:
                            risk_state = "risk_off"
                        elif vix < 15:
                            risk_state = "risk_on"
                    except (ValueError, TypeError):
                        pass

    return {
        "risk_state": risk_state,
        "volatility_regime": vol_regime,
        "event_window": event_window,
        "hours_until_event": hours_until_event,
    }
