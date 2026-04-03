"""Risk management — position sizing hints, stop/TP rule generation."""
import math
from app.features.base import FeatureSnapshot


class RiskManager:
    """
    Generates risk parameters (stop %, take-profit %, position size hint)
    based on market regime and volatility.

    All rules are regime-aware to avoid giving rigid stop distances that
    don't adapt to current market conditions.
    """

    BASE_STOP_PCT = 0.005    # 0.5% base stop (tightened from 1.5%)
    BASE_TP_PCT = 0.010      # 1.0% base take-profit (tightened from 2.5%)
    ATR_MULTIPLIER = 1.0     # reduced from 2.0
    TP_RATIO = 1.2           # TP = stop * 1.2 (tightened from 1.5x)

    def compute_stop_distance(self, features: FeatureSnapshot, horizon_hours: int = 4) -> float:
        """
        Compute stop-loss distance as a fraction of entry price.

        Uses hourly volatility (derived from annualized vol) scaled by horizon,
        then multiplied by ATR-style multiplier and regime adjustment.
        """
        # Convert annualized vol to hourly vol: hourly = ann_vol / sqrt(252 * 24)
        hourly_vol = features.volatility_4h / math.sqrt(252 * 24)
        # Scale by sqrt(horizon) — volatility scales with time
        vol_scaled = hourly_vol * math.sqrt(horizon_hours)
        # Apply ATR-style multiplier (2.0x) and regime scaling
        vol_multiplier = {
            "low": 0.8,
            "normal": 1.0,
            "high": 1.5,
        }.get(features.volatility_regime, 1.0)
        stop_distance = vol_scaled * self.ATR_MULTIPLIER * vol_multiplier
        # Fall back to base stop if computed distance is unreasonably small
        return max(stop_distance, self.BASE_STOP_PCT * vol_multiplier)

    def compute_take_profit_distance(self, features: FeatureSnapshot, horizon_hours: int = 4) -> float:
        """Compute take-profit distance scaled by confidence and regime."""
        hourly_vol = features.volatility_4h / math.sqrt(252 * 24)
        vol_scaled = hourly_vol * math.sqrt(horizon_hours)
        vol_multiplier = {
            "low": 0.8,
            "normal": 1.0,
            "high": 1.5,
        }.get(features.volatility_regime, 1.0)
        tp = vol_scaled * self.ATR_MULTIPLIER * vol_multiplier * self.TP_RATIO
        # Scale by confidence: low confidence → tighter TP
        tp *= max(0.5, features.confidence_score)
        # Fall back to base TP if unreasonably small
        base_tp = self.BASE_TP_PCT * vol_multiplier
        return max(tp, base_tp)

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
        """生成止损规则（中文）。"""
        stop_price = round(entry_price * (1 - stop_pct), 2)
        return f"若价格跌破 ${stop_price}，则止损出局（从入场价回落 {stop_pct*100:.1f}%）"

    def generate_tp_rule(self, entry_price: float, tp_pct: float, stance: str) -> str:
        """生成止盈规则（中文）。"""
        if stance == "long":
            tp_price = round(entry_price * (1 + tp_pct), 2)
        elif stance == "short":
            tp_price = round(entry_price * (1 - tp_pct), 2)
        else:
            return "中立立场，不设止盈。"

        return f"若价格达到 ${tp_price}，则止盈出局（从入场价获利 {tp_pct*100:.1f}%）"
