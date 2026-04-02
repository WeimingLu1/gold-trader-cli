"""FeatureSnapshot — unified Pydantic schema for all features."""
from pydantic import BaseModel, Field
from datetime import datetime


class FeatureSnapshot(BaseModel):
    """
    All features used for a single prediction, collected at snapshot time.

    This is the single input schema fed to the LLM Analyst and Strategy Scorer.
    Every field is typed for clarity and testing.
    """

    # ── Timestamps ────────────────────────────────────────────────────────────
    snapshot_at: datetime
    xau_price: float
    xau_price_fetched_at: datetime

    # ── Market features ───────────────────────────────────────────────────────
    returns_1h: float = 0.0
    returns_4h: float = 0.0
    returns_12h: float = 0.0
    returns_24h: float = 0.0
    volatility_4h: float = 0.0       # annualized volatility estimate
    volatility_24h: float = 0.0
    trend_state: str = "neutral"     # bullish | bearish | neutral

    # ── Macro features ─────────────────────────────────────────────────────────
    dxy_change: float = 0.0         # DXY % change over lookback
    yield_10y_change: float = 0.0   # 10y yield change (bp)
    real_rate_proxy: float = 0.0    # approx real rate %
    yield_curve_slope: float = 0.0  # 10y - 2y spread

    # ── News features ──────────────────────────────────────────────────────────
    news_sentiment_score: float = 0.0   # -1.0 (bearish) to +1.0 (bullish)
    news_event_intensity: float = 0.0   # 0.0 to 1.0
    is_gold_key_driver: bool = False    # any headline directly mentions gold drivers

    # ── Regime features ────────────────────────────────────────────────────────
    risk_state: str = "neutral"         # risk-on | risk-off | neutral
    volatility_regime: str = "normal"   # high | normal | low
    event_window: bool = False          # True if high-impact event within 24h

    # ── Positioning features ───────────────────────────────────────────────────
    cot_net_positions: float = 0.0
    etf_flow_24h: float = 0.0           # oz, + = inflow

    # ── Metadata ───────────────────────────────────────────────────────────────
    confidence_score: float = 0.5       # 0.0 to 1.0, how confident we are
    data_completeness: float = 1.0      # 0.0 to 1.0, fraction of data available
