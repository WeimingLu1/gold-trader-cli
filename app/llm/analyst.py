"""LLM Analyst — studies features and produces structured market analysis."""
from datetime import datetime
from app.features.base import FeatureSnapshot
from app.llm.provider import LLMProvider
from app.llm.schemas import AnalystOutput
from app.llm.prompts.analyst_prompt import build_analyst_prompt


class Analyst:
    """
    LLM-powered market analyst.

    Takes a FeatureSnapshot and produces an AnalystOutput with:
    - Direction bias (bullish/bearish/neutral)
    - Confidence level
    - Primary and counter drivers
    - Narrative explanation
    """

    PROMPT_VERSION = "v1.0"

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def analyze(self, features: FeatureSnapshot) -> AnalystOutput:
        """
        Run the analyst on a feature snapshot.

        Args:
            features: The FeatureSnapshot to analyze.

        Returns:
            AnalystOutput with structured market analysis.
        """
        prompt = build_analyst_prompt(features)
        response = await self.provider.generate(prompt)

        parsed = response.parsed or {}

        return AnalystOutput(
            generated_at=datetime.utcnow(),
            direction=parsed.get("direction", "neutral"),
            confidence=float(parsed.get("confidence", 0.5)),
            primary_drivers=parsed.get("primary_drivers", []),
            counter_drivers=parsed.get("counter_drivers", []),
            narrative=parsed.get("narrative", ""),
            key_events=parsed.get("key_events", []),
        )
