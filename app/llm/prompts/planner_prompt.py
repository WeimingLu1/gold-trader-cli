"""Planner prompt builder — constructs the LLM prompt for trade plan justification."""
from app.features.base import FeatureSnapshot
from app.llm.schemas import AnalystOutput


SYSTEM_PROMPT = """You are a trading strategy explainer. Given the market analysis and scoring data, explain WHY the computed stance (long/short/neutral) makes sense.

OUTPUT FORMAT: Return a JSON object with this field:
- justification: string (2-3 sentences) explaining the rationale for the stance

IMPORTANT:
- The stance has ALREADY been decided by the rule engine. Do NOT change it.
- Your job is only to explain WHY this stance is appropriate.
- Keep it concise and factual.
"""


USER_TEMPLATE = """## Market Analyst Output

- Direction: **{direction}**
- Confidence: {confidence:.2f}
- Narrative: {narrative}
- Primary drivers: {primary_drivers}
- Counter drivers: {counter_drivers}

## Scoring Breakdown (composite score: {composite_score:+.3f})

{factor_breakdown}

## Proposed Stance: **{stance}**

## Current Conditions
- Price: ${xau_price:.2f}
- Volatility regime: {volatility_regime}
- Risk state: {risk_state}
- Event window: {event_window}

Explain why the {stance} stance is appropriate given the above data. Respond with JSON."""


def build_planner_prompt(
    features: FeatureSnapshot,
    analyst: AnalystOutput,
    composite_score: float,
    stance: str,
    factor_scores: dict[str, float],
) -> str:
    """Build the planner prompt."""
    breakdown_lines = [f"- {k}: {v:+.3f}" for k, v in factor_scores.items()]
    breakdown = "\n".join(breakdown_lines)

    user = USER_TEMPLATE.format(
        direction=analyst.direction,
        confidence=analyst.confidence,
        narrative=analyst.narrative,
        primary_drivers=", ".join(analyst.primary_drivers) or "none",
        counter_drivers=", ".join(analyst.counter_drivers) or "none",
        composite_score=composite_score,
        factor_breakdown=breakdown,
        stance=stance,
        xau_price=features.xau_price,
        volatility_regime=features.volatility_regime,
        risk_state=features.risk_state,
        event_window="YES" if features.event_window else "NO",
    )
    return f"{SYSTEM_PROMPT}\n\n{user}"
