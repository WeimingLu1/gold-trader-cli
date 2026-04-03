"""Multi-factor scoring engine — converts FeatureSnapshot into a composite score."""
from app.features.base import FeatureSnapshot
from app.strategy.weights import FactorWeights


class Scorer:
    """
    Converts a FeatureSnapshot into a weighted composite score.

    composite_score range: -1.0 (strongly bearish) to +1.0 (strongly bullish)
    """

    def __init__(self, weights: FactorWeights):
        self.weights = weights

    def score(self, features: FeatureSnapshot) -> tuple[float, dict[str, float]]:
        """
        Compute factor-level scores and the final composite score.

        Returns:
            (composite_score, factor_scores dict) where factor_scores has per-factor values.
        """
        fs = features

        # ── Factor 1: USD (DXY) — gold is negatively correlated with USD ─────────
        # DXY up → gold down (score negative), DXY down → gold up (score positive)
        # dxy_change is in percent units (e.g. 0.192 for 0.192%); scale so ±0.3% → ±0.222
        # (matching 22.2% weight → ±0.222 max contribution, same scale as technical factor)
        factor_usd = -fs.dxy_change / 1.35

        # ── Factor 2: Real rates — gold yields zero coupon, real rates up → gold down
        # real_rate_proxy is in percent (e.g. 2.030 for 2.030%); scale so ±2% → ±0.222
        factor_real_rate = -fs.real_rate_proxy / 9.0

        # ── Factor 3: Positioning / COT — extreme net positioning signals reversals
        # Long squeeze risk: very high net long → slightly negative signal
        cot_signal = 0.0
        if fs.cot_net_positions > 250_000:
            cot_signal = -0.5
        elif fs.cot_net_positions < -250_000:
            cot_signal = 0.5
        factor_positioning = cot_signal

        # ── Factor 4: Volatility — high vol regime → reduce confidence / signal strength
        vol_signal = 0.0
        if fs.volatility_regime == "high":
            vol_signal = -0.3
        elif fs.volatility_regime == "low":
            vol_signal = 0.1
        factor_volatility = vol_signal

        # ── Factor 5: Technical — trend state from price momentum
        # Require r4 + r24 confirm for strong signal; neutral trend reduces strength
        trend_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
        base_tech = trend_map.get(fs.trend_state, 0.0)
        # Downgrade neutral trend signal; require r24 direction confirm for strong calls
        if fs.trend_state == "neutral":
            if fs.returns_24h > 0.003:      # 24h still up → downgrade bullish
                base_tech = 0.2
            elif fs.returns_24h < -0.003:  # 24h down → downgrade bearish
                base_tech = -0.2
        factor_technical = base_tech

        # ── Factor 6: News sentiment — NLP-derived score
        factor_news = fs.news_sentiment_score

        factor_scores = {
            "usd": factor_usd,
            "real_rate": factor_real_rate,
            "positioning": factor_positioning,
            "volatility": factor_volatility,
            "technical": factor_technical,
            "news": factor_news,
        }

        # Clamp factor scores to [-1, 1] before weighting
        clamped = {k: max(-1.0, min(1.0, v)) for k, v in factor_scores.items()}

        composite = (
            clamped["usd"] * self.weights.usd_factor
            + clamped["real_rate"] * self.weights.real_rate_factor
            + clamped["positioning"] * self.weights.positioning_factor
            + clamped["volatility"] * self.weights.volatility_factor
            + clamped["technical"] * self.weights.technical_factor
            + clamped["news"] * self.weights.news_factor
        )

        # Clamp composite to [-1, 1]
        composite = max(-1.0, min(1.0, composite))

        return composite, factor_scores
