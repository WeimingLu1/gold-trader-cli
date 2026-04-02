"""News-derived features from collected headlines."""
from app.features.base import FeatureSnapshot
from app.collectors.base import CollectedData


def build_news_features(news_items: list[CollectedData]) -> dict:
    """
    Aggregate collected news items into sentiment and intensity scores.

    In production, replace placeholder sentiment scoring with:
      - FinBERT (NLP model for financial sentiment)
      - VADER (规则化情感分析)
      - News API sentiment scores

    Args:
        news_items: List of CollectedData from NewsCollector.

    Returns:
        Dict of news feature fields compatible with FeatureSnapshot.
    """
    if not news_items:
        return {
            "news_sentiment_score": 0.0,
            "news_event_intensity": 0.0,
            "is_gold_key_driver": False,
        }

    # Placeholder: average normalized sentiment from mock data
    sentiment_scores = [
        item.normalized_payload.get("sentiment_score", 0.0)
        for item in news_items
        if item.normalized_payload
    ]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

    gold_key_driven = any(
        item.normalized_payload.get("is_gold_key_driver", False)
        for item in news_items
        if item.normalized_payload
    )

    # Event intensity: higher if more gold-key-driver headlines
    gold_drivens = sum(
        1 for item in news_items
        if item.normalized_payload and item.normalized_payload.get("is_gold_key_driver")
    )
    intensity = min(gold_drivens / max(len(news_items), 1) + 0.3, 1.0)

    return {
        "news_sentiment_score": avg_sentiment,
        "news_event_intensity": intensity,
        "is_gold_key_driver": gold_key_driven,
    }
