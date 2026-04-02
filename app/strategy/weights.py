"""Strategy weights — configurable factor weights for the scoring system."""
from pathlib import Path
from pydantic import BaseModel, Field
import yaml


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


def load_weights_from_yaml(path: str | Path) -> FactorWeights:
    """
    Load FactorWeights from a YAML file.

    Args:
        path: Path to the weights.yaml file.

    Returns:
        FactorWeights instance populated from the YAML.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Weights file not found: {p}")

    with open(p) as f:
        data = yaml.safe_load(f)

    return FactorWeights(
        usd_factor=data.get("usd_factor", 0.20),
        real_rate_factor=data.get("real_rate_factor", 0.20),
        positioning_factor=data.get("positioning_factor", 0.15),
        volatility_factor=data.get("volatility_factor", 0.15),
        technical_factor=data.get("technical_factor", 0.20),
        news_factor=data.get("news_factor", 0.10),
    )


def get_weights(weights_file: str | Path | None = None) -> FactorWeights:
    """
    Get FactorWeights, loading from YAML if a path is provided.
    Falls back to hardcoded defaults if file not found.
    """
    if weights_file:
        try:
            return load_weights_from_yaml(weights_file)
        except FileNotFoundError:
            pass
    return FactorWeights()


# Lazy-load DEFAULT_WEIGHTS from weights.yaml relative to this file's location.
_DEFAULT_WEIGHTS_PATH = Path(__file__).parent.parent.parent / "config" / "weights.yaml"
DEFAULT_WEIGHTS = get_weights(_DEFAULT_WEIGHTS_PATH)
