"""Strategy weights — configurable factor weights for the scoring system."""
from pydantic import BaseModel, Field


class FactorWeights(BaseModel):
    """
    Weights for each factor in the composite score.
    All weights should sum to 1.0.

    These are loaded from config/weights.yaml at startup and
    versioned in the strategy_versions table when changed.
    """

    usd_factor: float = Field(default=0.20, ge=0.0, le=1.0)
    real_rate_factor: float = Field(default=0.20, ge=0.0, le=1.0)
    positioning_factor: float = Field(default=0.15, ge=0.0, le=1.0)
    volatility_factor: float = Field(default=0.15, ge=0.0, le=1.0)
    technical_factor: float = Field(default=0.20, ge=0.0, le=1.0)
    news_factor: float = Field(default=0.10, ge=0.0, le=1.0)

    def validate_sum(self) -> bool:
        total = (
            self.usd_factor
            + self.real_rate_factor
            + self.positioning_factor
            + self.volatility_factor
            + self.technical_factor
            + self.news_factor
        )
        return abs(total - 1.0) < 1e-6


DEFAULT_WEIGHTS = FactorWeights()
