"""Regime detection features — risk state, volatility regime, event windows."""
from app.features.base import FeatureSnapshot
from app.collectors.base import CollectedData


def build_regime_features(
    volatility_24h: float,
    macro_events: list[CollectedData],
    risk_assets: list[CollectedData] | None = None,  # e.g. SPY, VIX
) -> dict:
    """
    Classify market regime based on volatility, macro calendar, and risk assets.

    Args:
        volatility_24h: 24h annualized volatility from market_features.
        macro_events: Upcoming macro events from MacroCalendarCollector.
        risk_assets: Optional price/change data for risk-asset proxies.

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
    has_high_impact = any(
        ev.normalized_payload and ev.normalized_payload.get("is_high_impact", False)
        for ev in macro_events
    )
    event_window = has_high_impact

    # ── Risk state ───────────────────────────────────────────────────────────
    # In production: analyze VIX, high-yield bonds, EM currencies
    # Stub: neutral by default
    risk_state = "neutral"

    return {
        "risk_state": risk_state,
        "volatility_regime": vol_regime,
        "event_window": event_window,
    }
