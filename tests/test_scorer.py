"""Tests for the strategy scoring engine."""
from datetime import datetime, timezone
from app.features.base import FeatureSnapshot
from app.strategy.scorer import Scorer
from app.strategy.weights import DEFAULT_WEIGHTS, FactorWeights


def test_scorer_score_range():
    """Composite score must always be in [-1, 1]."""
    snap = FeatureSnapshot(
        snapshot_at=datetime.utcnow(),
        xau_price=2345.0,
        xau_price_fetched_at=datetime.utcnow(),
        dxy_change=0.01,
        real_rate_proxy=-0.02,
        trend_state="bullish",
        news_sentiment_score=0.5,
        volatility_regime="normal",
        event_window=False,
        data_completeness=1.0,
        confidence_score=0.5,
    )
    scorer = Scorer(DEFAULT_WEIGHTS)
    score, factors = scorer.score(snap)

    assert -1.0 <= score <= 1.0
    assert isinstance(factors, dict)
    assert all(-1.0 <= v <= 1.0 for v in factors.values())


def test_scorer_bearish_dxy():
    """Strong DXY appreciation → negative score."""
    snap = FeatureSnapshot(
        snapshot_at=datetime.utcnow(),
        xau_price=2345.0,
        xau_price_fetched_at=datetime.utcnow(),
        dxy_change=0.03,      # 3% USD appreciation
        real_rate_proxy=0.0,
        trend_state="neutral",
        news_sentiment_score=0.0,
        volatility_regime="normal",
        event_window=False,
        data_completeness=1.0,
        confidence_score=0.5,
    )
    scorer = Scorer(DEFAULT_WEIGHTS)
    score, _ = scorer.score(snap)

    # USD up strongly → gold bearish → negative score
    assert score < 0


def test_scorer_bullish_trend():
    """Bullish trend state → positive technical factor."""
    snap = FeatureSnapshot(
        snapshot_at=datetime.utcnow(),
        xau_price=2345.0,
        xau_price_fetched_at=datetime.utcnow(),
        dxy_change=0.0,
        real_rate_proxy=0.0,
        trend_state="bullish",
        news_sentiment_score=0.0,
        volatility_regime="normal",
        event_window=False,
        data_completeness=1.0,
        confidence_score=0.5,
    )
    scorer = Scorer(DEFAULT_WEIGHTS)
    _, factors = scorer.score(snap)

    assert factors["technical"] == 1.0


def test_factor_weights_validate_sum():
    """Weights must sum to 1.0."""
    assert DEFAULT_WEIGHTS.validate_sum()


def test_custom_weights():
    """Custom weights should be usable in scorer."""
    custom = FactorWeights(
        usd_factor=0.3,
        real_rate_factor=0.3,
        positioning_factor=0.1,
        volatility_factor=0.1,
        technical_factor=0.1,
        news_factor=0.1,
    )
    assert custom.validate_sum()

    snap = FeatureSnapshot(
        snapshot_at=datetime.utcnow(),
        xau_price=2345.0,
        xau_price_fetched_at=datetime.utcnow(),
        dxy_change=0.0,
        real_rate_proxy=0.0,
        trend_state="neutral",
        news_sentiment_score=0.0,
        volatility_regime="normal",
        event_window=False,
        data_completeness=1.0,
        confidence_score=0.5,
    )
    scorer = Scorer(custom)
    score, _ = scorer.score(snap)
    assert -1.0 <= score <= 1.0
