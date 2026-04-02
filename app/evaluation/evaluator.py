"""Evaluator — post-hoc evaluation of matured snapshots against actual prices."""
from datetime import datetime
from app.db.models import Snapshot, Evaluation
from app.db.repo import EvaluationRepo


class Evaluator:
    """
    Evaluates a snapshot's trade plan once its prediction horizon has elapsed.

    Evaluation compares:
    1. Predicted direction (long/short/neutral) vs actual direction
    2. Whether stop-loss or take-profit was hit first (if directional)
    3. Expected return vs actual return
    """

    DIRECTION_TOLERANCE = 0.001  # 0.1% — threshold to call it "up" vs "flat"

    def evaluate(self, snap: Snapshot, current_price: float) -> Evaluation:
        """
        Evaluate a single snapshot against the current XAU price.

        Args:
            snap: The Snapshot record with trade_plan_json.
            current_price: XAUUSD price at evaluation time (horizon elapsed).

        Returns:
            Populated Evaluation object (not yet committed to DB).
        """
        entry_price = snap.xau_price
        plan = snap.trade_plan_json or {}
        stance = plan.get("stance", "neutral")

        # ── Direction ─────────────────────────────────────────────────────────────
        price_change_pct = (current_price - entry_price) / entry_price
        if price_change_pct > self.DIRECTION_TOLERANCE:
            direction_actual = "up"
        elif price_change_pct < -self.DIRECTION_TOLERANCE:
            direction_actual = "down"
        else:
            direction_actual = "flat"

        # Direction hit
        if stance == "neutral":
            direction_hit = None
        elif stance == "long":
            direction_hit = direction_actual == "up"
        elif stance == "short":
            direction_hit = direction_actual == "down"
        else:
            direction_hit = None

        # ── Stop / TP evaluation ─────────────────────────────────────────────────
        stop_rule = plan.get("stop_rule", "")
        tp_rule = plan.get("take_profit_rule", "")
        stop_hit = self._evaluate_stop_tp(
            stance, entry_price, current_price, stop_rule, tp_rule, plan
        )

        # ── Returns ───────────────────────────────────────────────────────────────
        actual_return = round(price_change_pct * 100, 4)  # percentage
        expected_return = plan.get("expected_return_pct", 0.0)

        eval_ = Evaluation(
            snapshot_id=snap.id,
            xau_price_at_horizon=current_price,
            direction_actual=direction_actual,
            direction_hit=direction_hit,
            stop_hit=stop_hit,
            expected_return=expected_return,
            actual_return=actual_return,
            prompt_version=snap.prompt_version,
            model_version=snap.model_version,
            strategy_version=snap.strategy_version,
        )
        return eval_

    def _evaluate_stop_tp(
        self,
        stance: str,
        entry_price: float,
        current_price: float,
        stop_rule: str,
        tp_rule: str,
        plan: dict,
    ) -> str:
        """Determine whether stop-loss or take-profit was hit first."""
        if stance == "neutral" or not stop_rule:
            return "neither"

        # Extract prices from rules (simple regex for "$2345.00" patterns)
        import re

        def extract_price(rule: str) -> float | None:
            m = re.search(r"\$(\d+\.?\d*)", rule)
            return float(m.group(1)) if m else None

        stop_price = extract_price(stop_rule)
        tp_price = extract_price(tp_rule)

        if stop_price is None and tp_price is None:
            return "neither"

        if stance == "long":
            if tp_price and current_price >= tp_price:
                return "tp"
            if stop_price and current_price <= stop_price:
                return "stop"
        elif stance == "short":
            if tp_price and current_price <= tp_price:
                return "tp"
            if stop_price and current_price >= stop_price:
                return "stop"

        return "neither"
