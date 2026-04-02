"""Tests for feature engineering modules."""
from datetime import datetime, timedelta, timezone
from app.features.market_features import build_market_features
from app.features.regime_features import build_regime_features
from app.collectors.base import CollectedData


def test_build_market_features_basic():
    """Test that market features compute returns correctly."""
    now = datetime.now(timezone.utc)
    hist = {
        now - timedelta(hours=1): 2340.0,
        now - timedelta(hours=4): 2330.0,
        now - timedelta(hours=12): 2320.0,
        now - timedelta(hours=24): 2310.0,
    }
    features = build_market_features(2345.50, hist, now)

    assert "returns_1h" in features
    assert "returns_4h" in features
    assert "returns_12h" in features
    assert "returns_24h" in features
    assert "trend_state" in features
    assert features["trend_state"] in ["bullish", "bearish", "neutral"]
    assert features["returns_1h"] > 0  # 2345.5 > 2340


def test_build_market_features_missing_history():
    """Test graceful handling when history is sparse."""
    now = datetime.now(timezone.utc)
    hist = {}
    features = build_market_features(2345.50, hist, now)

    assert features["returns_1h"] == 0.0
    assert features["returns_4h"] == 0.0
    assert features["volatility_4h"] == 0.0
    assert features["trend_state"] == "neutral"


def test_build_regime_features():
    """Test regime detection."""
    high_vol_events = [
        CollectedData(
            source="test",
            symbol=None,
            event_time=datetime.now(timezone.utc),
            available_time=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            raw_payload={},
            normalized_payload={"is_high_impact": True, "hours_until_event": 2.0},
        )
    ]

    feats = build_regime_features(volatility_24h=0.25, macro_events=high_vol_events)
    assert feats["volatility_regime"] == "high"
    assert feats["event_window"] is True

    low_vol_feats = build_regime_features(volatility_24h=0.05, macro_events=[])
    assert low_vol_feats["volatility_regime"] == "low"
    assert low_vol_feats["event_window"] is False
