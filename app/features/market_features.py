"""Market-derived features from price history."""
from datetime import datetime, timedelta
from app.features.base import FeatureSnapshot


def build_market_features(
    current_price: float,
    historical_prices: dict[datetime, float],
    fetched_at: datetime,
) -> dict:
    """
    Compute returns, volatility, and trend state from historical price data.

    Args:
        current_price: Latest XAUUSD price.
        historical_prices: Dict of {timestamp: price}, at least 24h of data.
        fetched_at: Time when current_price was captured.

    Returns:
        Dict of market feature fields compatible with FeatureSnapshot.
    """

    def calc_return(hours: int) -> float:
        target = fetched_at - timedelta(hours=hours)
        # Find closest timestamp within ±15min
        closest = min(
            historical_prices.keys(),
            key=lambda t: abs((t - target).total_seconds()),
            default=None,
        )
        if closest is None:
            return 0.0
        past_price = historical_prices[closest]
        return (current_price - past_price) / past_price if past_price else 0.0

    def calc_volatility(hours: int) -> float:
        cutoff = fetched_at - timedelta(hours=hours)
        relevant = {t: p for t, p in historical_prices.items() if t >= cutoff}
        if len(relevant) < 3:
            return 0.0
        sorted_prices = sorted(relevant.values())
        returns = [
            (sorted_prices[i] - sorted_prices[i - 1]) / sorted_prices[i - 1]
            for i in range(1, len(sorted_prices))
        ]
        if not returns:
            return 0.0
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        # Annualize: sqrt(252 * hourly_var) ≈ hourly_std * sqrt(252)
        return (variance ** 0.5) * (252 ** 0.5)

    r1 = calc_return(1)
    r4 = calc_return(4)
    r12 = calc_return(12)
    r24 = calc_return(24)

    vol4 = calc_volatility(4)
    vol24 = calc_volatility(24)

    # Threshold for trending: require meaningful 4h move
    # In a +125%/month regime, small pullbacks (<0.8%) shouldn't trigger bearish
    if r4 > 0.005:
        trend = "bullish"
    elif r4 < -0.010:   # require deeper pullback for bearish (was -0.005)
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "returns_1h": r1,
        "returns_4h": r4,
        "returns_12h": r12,
        "returns_24h": r24,
        "volatility_4h": vol4,
        "volatility_24h": vol24,
        "trend_state": trend,
    }
