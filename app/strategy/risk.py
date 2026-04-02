"""Risk management — position sizing hints, stop/TP rule generation."""
from app.features.base import FeatureSnapshot


class RiskManager:
    """
    Generates risk parameters (stop %, take-profit %, position size hint)
    based on market regime and volatility.

    All rules are regime-aware to avoid giving rigid stop distances that
    don't adapt to current market conditions.
    """

    BASE_STOP_PCT = 0.015    # 1.5% base stop
    BASE_TP_PCT = 0.025      # 2.5% base take-profit
    ATR_MULTIPLIER = 2.0

    def compute_stop_distance(self, features: FeatureSnapshot) -> float:
        """
        Compute stop-loss distance as a fraction of entry price.

        In production: use ATR (Average True Range) from price data.
        For now, scale by volatility regime.
        """
        vol_multiplier = {
            "low": 0.8,
            "normal": 1.0,
            "high": 1.5,
        }.get(features.volatility_regime, 1.0)

        # High volatility regime → wider stops
        if features.volatility_regime == "high":
            return self.BASE_STOP_PCT * 1.5
        elif features.volatility_regime == "low":
            return self.BASE_STOP_PCT * 0.8
        return self.BASE_STOP_PCT

    def compute_take_profit_distance(self, features: FeatureSnapshot) -> float:
        """Compute take-profit distance scaled by confidence and regime."""
        vol_multiplier = {
            "low": 0.8,
            "normal": 1.0,
            "high": 1.5,
        }.get(features.volatility_regime, 1.0)

        tp = self.BASE_TP_PCT * vol_multiplier

        # Scale by confidence: low confidence → tighter TP
        tp *= max(0.5, features.confidence_score)

        return tp

    def adjust_confidence(self, features: FeatureSnapshot) -> float:
        """
        Reduce confidence under adverse conditions.

        This is applied before score → stance mapping to ensure
        low-confidence signals don't generate directional trades.
        """
        confidence = features.confidence_score

        if features.volatility_regime == "high":
            confidence *= 0.8
        if features.event_window:
            confidence *= 0.7
        if features.data_completeness < 0.5:
            confidence = min(confidence, 0.3)

        return max(0.0, min(1.0, confidence))

    def generate_stop_rule(self, entry_price: float, stop_pct: float) -> str:
        """Generate a human-readable stop-loss rule."""
        stop_price = round(entry_price * (1 - stop_pct), 2)
        return f"Exit if price falls below ${stop_price} (${stop_pct*100:.1f}% drawdown from entry)"

    def generate_tp_rule(self, entry_price: float, tp_pct: float, stance: str) -> str:
        """Generate a human-readable take-profit rule."""
        if stance == "long":
            tp_price = round(entry_price * (1 + tp_pct), 2)
        elif stance == "short":
            tp_price = round(entry_price * (1 - tp_pct), 2)
        else:
            return "No take-profit rule for neutral stance."

        return f"Exit if price reaches ${tp_price} (${tp_pct*100:.1f}% gain from entry)"
