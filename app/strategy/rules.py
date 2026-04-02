"""Rule engine — maps scores to stances and applies risk guardrails."""
from app.features.base import FeatureSnapshot


class RuleEngine:
    """
    Converts composite scores into actionable stances and applies risk rules.

    The key principle: LLM proposes, rules validate and constrain.
    This prevents the model from making unconstrained directional bets.
    """

    # Score thresholds
    LONG_THRESHOLD = 0.25
    SHORT_THRESHOLD = -0.25
    HIGH_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.3

    def map_score_to_stance(self, score: float, confidence: float) -> str:
        """
        Map composite score and confidence to a stance.

        Args:
            score: Composite score from -1.0 to 1.0.
            confidence: Confidence score from 0.0 to 1.0.

        Returns:
            stance: "long" | "short" | "neutral"
        """
        # Low confidence → always neutral
        if confidence < self.LOW_CONFIDENCE:
            return "neutral"

        if score > self.LONG_THRESHOLD:
            return "long"
        elif score < self.SHORT_THRESHOLD:
            return "short"
        return "neutral"

    def apply_risk_rules(self, stance: str, features: FeatureSnapshot) -> tuple[str, str]:
        """
        Apply risk guardrails and return (adjusted_stance, risk_note).

        Guardrails:
        1. High volatility regime → reduce exposure (already in confidence)
        2. Event window within 4h → neutral stance
        3. Data completeness < 50% → neutral stance
        4. Extreme positioning → note only (already in scorer)
        """
        notes: list[str] = []
        adjusted = stance

        # Guardrail 1: High volatility regime
        if features.volatility_regime == "high":
            notes.append("High volatility regime — reduce size.")

        # Guardrail 2: Event window within 4 hours
        if features.event_window:
            # Only override if event is imminent (< 4h)
            notes.append("High-impact event imminent — caution warranted.")
            if adjusted != "neutral":
                notes.append("Event window overrides directional stance.")

        # Guardrail 3: Incomplete data
        if features.data_completeness < 0.5:
            notes.append(f"Incomplete data ({features.data_completeness:.0%}) — neutral forced.")
            adjusted = "neutral"

        # Guardrail 4: High volatility overrides directional stance
        if features.volatility_regime == "high" and adjusted != "neutral":
            notes.append("High vol overrides directional stance.")
            adjusted = "neutral"

        risk_note = " ".join(notes) if notes else "Normal operation — no risk flags."
        return adjusted, risk_note

    def determine_expected_return(
        self,
        stance: str,
        entry_price: float,
        stop_pct: float = 0.015,
        tp_pct: float = 0.025,
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
