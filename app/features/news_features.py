"""News-derived features from collected headlines."""
from app.features.base import FeatureSnapshot
from app.collectors.base import CollectedData

# Keyword lists for rule-based sentiment scoring
_POSITIVE_KEYWORDS = [
    "surge", "rally", "gains", "bullish", "record high", "record peak",
    "buying", "safe haven", "climbs", "rises", "soars", "jumps",
    "strength", "support", "upside", "growth", "demand",
]
_NEGATIVE_KEYWORDS = [
    "plunge", "fall", "drop", "bearish", "selling", "risk-on",
    "declines", "falls", "tumbles", "slumps", "losses",
    "weakness", "resistance", "downside", "headwinds", "pressured",
    "rate hike", "tightening", "dollar strength",
]


def _score_headline_sentiment(headline: str) -> float:
    """
    Score a single headline's sentiment using keyword matching.

    Returns a float in [-1.0, 1.0].
    """
    text = headline.lower()
    positive = sum(1 for w in _POSITIVE_KEYWORDS if w in text)
    negative = sum(1 for w in _NEGATIVE_KEYWORDS if w in text)
    if positive > negative:
        return min(1.0, 0.25 * positive)
    elif negative > positive:
        return max(-1.0, -0.25 * negative)
    return 0.0


def build_news_features(news_items: list[CollectedData]) -> dict:
    """
    Aggregate collected news items into sentiment and intensity scores.

    Uses keyword-based rule scoring (no NLP model required).
    Positive keywords: surge, rally, gains, bullish, record high...
    Negative keywords: plunge, fall, drop, bearish, selling...

    Args:
        news_items: List of CollectedData from NewsCollector.
                    Each item's normalized_payload should have: headline, is_gold_key_driver.

    Returns:
        Dict of news feature fields compatible with FeatureSnapshot.
    """
    if not news_items:
        return {
            "news_sentiment_score": 0.0,
            "news_event_intensity": 0.0,
            "is_gold_key_driver": False,
        }

    # Score each headline using keyword-based sentiment
    sentiment_scores = []
    gold_key_driven_count = 0

    for item in news_items:
        if not item.normalized_payload:
            continue
        headline = item.normalized_payload.get("headline", "")
        if not headline:
            continue

        sentiment_scores.append(_score_headline_sentiment(headline))
        if item.normalized_payload.get("is_gold_key_driver"):
            gold_key_driven_count += 1

    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
    ratio = gold_key_driven_count / max(len(news_items), 1)
    intensity = min(ratio + 0.2, 1.0)

    return {
        "news_sentiment_score": avg_sentiment,
        "news_event_intensity": intensity,
        "is_gold_key_driver": gold_key_driven_count > 0,
    }


def build_news_features_from_headlines(headlines: list[dict]) -> dict:
    """
    Build news features from a list of headline dicts (used by backtest engine).

    Args:
        headlines: List of dicts with keys: headline, source, url.

    Returns:
        Dict compatible with FeatureSnapshot news fields.
    """
    if not headlines:
        return {
            "news_sentiment_score": 0.0,
            "news_event_intensity": 0.0,
            "is_gold_key_driver": False,
        }

    gold_keywords = [
        "gold", "xauusd", "goldman sachs", "fed", "treasury",
        "inflation", "deflation", "dollar", "dxy", "risk-off",
        "safe haven", "central bank", "pbc", "ecb", "fomc",
        "nonfarm payrolls", "cpi", "ppi", "gdp", "xau",
    ]

    def is_gold_key(h: str) -> bool:
        return any(kw in h.lower() for kw in gold_keywords)

    sentiment_scores = [_score_headline_sentiment(h.get("headline", "")) for h in headlines]
    gold_count = sum(1 for h in headlines if is_gold_key(h.get("headline", "")))
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
    ratio = gold_count / max(len(headlines), 1)
    intensity = min(ratio + 0.2, 1.0)

    return {
        "news_sentiment_score": avg_sentiment,
        "news_event_intensity": intensity,
        "is_gold_key_driver": gold_count > 0,
    }
