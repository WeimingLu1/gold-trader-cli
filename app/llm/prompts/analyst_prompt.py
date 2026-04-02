"""Analyst prompt builder — constructs the LLM prompt for market analysis."""
from app.features.base import FeatureSnapshot


SYSTEM_PROMPT = """You are a gold (XAUUSD) market analyst. Your role is to:
1. Study the provided market features and identify key patterns.
2. Determine if near-term gold price bias is bullish, bearish, or neutral.
3. Assign a confidence level (0.0-1.0).
4. List primary drivers and counter-drivers.
5. Write a concise narrative explaining your reasoning.

OUTPUT FORMAT: Return a JSON object with these fields:
- direction: "bullish" | "bearish" | "neutral"
- confidence: float between 0.0 and 1.0
- primary_drivers: list of strings
- counter_drivers: list of strings
- narrative: string (2-4 sentences)
- key_events: list of strings (event names)

IMPORTANT:
- Do NOT suggest specific entry/exit prices — that is handled by the planner.
- Do NOT make trading decisions — only analyze and explain.
- Be concise and evidence-based.
"""


USER_TEMPLATE = """## XAUUSD Market Snapshot

**Time:** {snapshot_time}
**Price:** ${xau_price:.2f}

### Returns & Trend
- 1h: {returns_1h:+.3%}
- 4h: {returns_4h:+.3%}
- 12h: {returns_12h:+.3%}
- 24h: {returns_24h:+.3%}
- Trend: **{trend_state}**
- Volatility 4h: {volatility_4h:.2%}
- Volatility 24h: {volatility_24h:.2%}

### Macro
- DXY change: {dxy_change:+.3%}
- 10Y yield change: {yield_10y_change:+.2f} bp
- Real rate proxy: {real_rate_proxy:+.3%}
- Yield curve slope: {yield_curve_slope:+.2f}

### News & Sentiment
- Sentiment score: {news_sentiment_score:+.2f} (range -1 to +1)
- Event intensity: {news_event_intensity:.2f}
- Gold key driver: {{"YES" if is_gold_key_driver else "NO"}}

### Regime
- Risk state: **{risk_state}**
- Vol regime: **{volatility_regime}**
- Event window: {{"YES" if event_window else "NO"}}

### Positioning
- COT net positions: {cot_net_positions:,.0f} contracts
- ETF flow 24h: {etf_flow_24h:,.0f} oz

### Data Quality
- Confidence score: {confidence_score:.2f}
- Data completeness: {data_completeness:.0%}

---

Analyze this data and produce your JSON output."""


def build_analyst_prompt(features: FeatureSnapshot) -> str:
    """Build the full analyst prompt from a FeatureSnapshot."""
    user = USER_TEMPLATE.format(
        snapshot_time=features.snapshot_at.strftime("%Y-%m-%d %H:%M UTC"),
        xau_price=features.xau_price,
        returns_1h=features.returns_1h,
        returns_4h=features.returns_4h,
        returns_12h=features.returns_12h,
        returns_24h=features.returns_24h,
        trend_state=features.trend_state,
        volatility_4h=features.volatility_4h,
        volatility_24h=features.volatility_24h,
        dxy_change=features.dxy_change,
        yield_10y_change=features.yield_10y_change,
        real_rate_proxy=features.real_rate_proxy,
        yield_curve_slope=features.yield_curve_slope,
        news_sentiment_score=features.news_sentiment_score,
        news_event_intensity=features.news_event_intensity,
        is_gold_key_driver=features.is_gold_key_driver,
        risk_state=features.risk_state,
        volatility_regime=features.volatility_regime,
        event_window=features.event_window,
        cot_net_positions=features.cot_net_positions,
        etf_flow_24h=features.etf_flow_24h,
        confidence_score=features.confidence_score,
        data_completeness=features.data_completeness,
    )
    return f"{SYSTEM_PROMPT}\n\n{user}"
