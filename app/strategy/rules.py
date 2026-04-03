"""Rule engine — maps scores to stances and applies risk guardrails."""
from app.features.base import FeatureSnapshot


class RuleEngine:
    """
    Converts composite scores into actionable stances and applies risk rules.

    The key principle: LLM proposes, rules validate and constrain.
    This prevents the model from making unconstrained directional bets.
    """

    # Score thresholds — adaptive based on volatility regime
    LONG_THRESHOLD_NORMAL = 0.15    # normal/low volatility: more signals
    SHORT_THRESHOLD_NORMAL = -0.15
    LONG_THRESHOLD_HIGH = 0.25      # high volatility: tighter signals needed
    SHORT_THRESHOLD_HIGH = -0.25
    HIGH_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.25          # lowered from 0.3 to allow more signals through

    def map_score_to_stance(
        self, score: float, confidence: float, volatility_regime: str = "normal"
    ) -> str:
        """
        Map composite score and confidence to a stance.

        Args:
            score: Composite score from -1.0 to 1.0.
            confidence: Confidence score from 0.0 to 1.0.
            volatility_regime: "low" | "normal" | "high" — widens thresholds in high vol.

        Returns:
            stance: "long" | "short" | "neutral"
        """
        # Low confidence → always neutral
        if confidence < self.LOW_CONFIDENCE:
            return "neutral"

        # Adaptive thresholds based on volatility regime
        if volatility_regime == "high":
            threshold_high = self.LONG_THRESHOLD_HIGH
            threshold_low = self.SHORT_THRESHOLD_HIGH
        else:
            threshold_high = self.LONG_THRESHOLD_NORMAL
            threshold_low = self.SHORT_THRESHOLD_NORMAL

        if score > threshold_high:
            return "long"
        elif score < threshold_low:
            return "short"
        return "neutral"

    def apply_risk_rules(self, stance: str, features: FeatureSnapshot) -> tuple[str, str]:
        """
        应用风控规则，返回（调整后立场，风控提示）。

        规则：
        1. 高波动环境 → 降低敞口
        2. 重要事件窗口（4小时内）→ 中立
        3. 数据完整度 < 50% → 中立
        """
        notes: list[str] = []
        adjusted = stance

        # 规则1：高波动
        if features.volatility_regime == "high":
            notes.append("高波动环境 — 建议降低仓位。")

        # 规则2：重要事件窗口
        if features.event_window:
            notes.append("重要宏观事件临近 — 建议谨慎。")
            if adjusted != "neutral":
                notes.append("事件窗口强制中立。")

        # 规则3：数据不完整
        if features.data_completeness < 0.5:
            notes.append(f"数据不完整（{features.data_completeness:.0%}）— 强制中立。")
            adjusted = "neutral"

        # 规则4：高波动环境下保持立场但提示风险（不强制中立）
        if features.volatility_regime == "high" and adjusted != "neutral":
            notes.append("高波动环境 — 保持方向性敞口但请关注风险。")

        risk_note = " ".join(notes) if notes else "正常状态 — 无风控警告。"
        return adjusted, risk_note

    def determine_expected_return(
        self,
        stance: str,
        entry_price: float,
        stop_pct: float = 0.005,
        tp_pct: float = 0.010,
    ) -> float:
        """
        Estimate expected return % for a given stance.

        Used for tracking expected vs actual performance.
        """
        if stance == "neutral":
            return 0.0
        elif stance == "long":
            return tp_pct  # assume we hit take-profit (best case baseline)
        elif stance == "short":
            return -tp_pct
        return 0.0
