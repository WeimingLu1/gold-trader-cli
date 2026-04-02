"""LLM Planner — converts analyst output into a structured trade plan."""
from datetime import datetime
from app.llm.provider import LLMProvider
from app.llm.schemas import AnalystOutput, TradePlan
from app.llm.prompts.planner_prompt import build_planner_prompt
from app.strategy.scorer import Scorer
from app.strategy.rules import RuleEngine
from app.strategy.risk import RiskManager
from app.strategy.weights import DEFAULT_WEIGHTS
from app.features.base import FeatureSnapshot


class Planner:
    """
    Trade planner — takes analyst output + features + rules → TradePlan.

    The planner does NOT let the LLM decide everything freely.
    Instead:
    1. The Scorer computes a composite score
    2. The RuleEngine maps score → stance and applies risk rules
    3. The RiskManager generates stop/TP distances
    4. The LLM provides narrative justification (the "why")
    """

    PROMPT_VERSION = "v1.0"
    STRATEGY_VERSION = "v1.0"

    def __init__(
        self,
        provider: LLMProvider,
        scorer: Scorer | None = None,
        rule_engine: RuleEngine | None = None,
        risk_manager: RiskManager | None = None,
    ):
        self.provider = provider
        self.scorer = scorer or Scorer(DEFAULT_WEIGHTS)
        self.rule_engine = rule_engine or RuleEngine()
        self.risk_manager = risk_manager or RiskManager()

    async def plan(
        self,
        features: FeatureSnapshot,
        analyst_output: AnalystOutput,
        snapshot_id: int,
        horizon_hours: int,
    ) -> TradePlan:
        """
        Generate a trade plan.

        Args:
            features: The FeatureSnapshot used for analysis.
            analyst_output: The structured output from the Analyst.
            snapshot_id: Database ID of the snapshot.
            horizon_hours: Prediction horizon in hours.

        Returns:
            TradePlan with all guidance fields.
        """
        # ── Step 1: Rule-based score → stance (not LLM's job) ─────────────────────
        composite_score, factor_scores = self.scorer.score(features)

        # Adjust confidence based on risk conditions
        adjusted_confidence = self.risk_manager.adjust_confidence(features)

        # Override analyst confidence with risk-adjusted version
        final_confidence = min(analyst_output.confidence, adjusted_confidence)

        stance = self.rule_engine.map_score_to_stance(composite_score, final_confidence)

        # ── Step 2: Apply risk guardrails ────────────────────────────────────────
        stance, risk_note = self.rule_engine.apply_risk_rules(stance, features)

        # ── Step 3: Generate stop / TP rules ────────────────────────────────────
        entry_price = features.xau_price
        stop_pct = self.risk_manager.compute_stop_distance(features)
        tp_pct = self.risk_manager.compute_take_profit_distance(features)

        stop_rule = self.risk_manager.generate_stop_rule(entry_price, stop_pct)
        tp_rule = self.risk_manager.generate_tp_rule(entry_price, tp_pct, stance)

        expected_return_pct = self.rule_engine.determine_expected_return(stance, entry_price)

        # ── Step 4: LLM provides the narrative "why" ─────────────────────────────
        why = await self._generate_narrative(
            features, analyst_output, composite_score, stance, factor_scores
        )

        return TradePlan(
            generated_at=datetime.utcnow(),
            snapshot_id=snapshot_id,
            stance=stance,
            horizon_hours=horizon_hours,
            confidence=round(final_confidence, 3),
            entry_rule=f"Enter when price returns to ${entry_price} level with confirmation.",
            stop_rule=stop_rule,
            take_profit_rule=tp_rule,
            invalidation_rule=self._build_invalidation_rule(features, stance),
            risk_note=risk_note,
            why=why,
            model_version=self.provider.MODEL_NAME if hasattr(self.provider, "MODEL_NAME") else "unknown",
            prompt_version=self.PROMPT_VERSION,
            strategy_version=self.STRATEGY_VERSION,
            expected_return_pct=expected_return_pct,
        )

    async def _generate_narrative(
        self,
        features: FeatureSnapshot,
        analyst: AnalystOutput,
        composite_score: float,
        stance: str,
        factor_scores: dict[str, float],
    ) -> str:
        """
        Use the LLM to produce a narrative justification for the trade plan.

        The LLM does NOT choose the stance — that is done by the rule engine.
        The LLM explains WHY this stance makes sense given the data.
        """
        prompt = build_planner_prompt(features, analyst, composite_score, stance, factor_scores)
        response = await self.provider.generate(prompt)
        return response.parsed.get("justification", analyst.narrative)

    def _build_invalidation_rule(self, features: FeatureSnapshot, stance: str) -> str:
        """Build the invalidation rule based on current regime."""
        rules = []
        if features.event_window:
            rules.append("High-impact event triggers unexpected vol spike.")
        if features.volatility_regime == "high":
            rules.append("Volatility regime shifts from high to extreme.")
        rules.append(f"{features.xau_price * 0.99:.2f} breach on stop or TP hit.")
        return " ".join(rules)
