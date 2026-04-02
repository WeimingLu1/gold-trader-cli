"""Tests for LLM schemas and provider output parsing."""
from datetime import datetime
from app.llm.schemas import AnalystOutput, TradePlan, LLMResponse
from app.llm.provider import MockLLMProvider


def test_analyst_output_to_dict():
    """AnalystOutput.to_dict() should produce a serializable dict."""
    output = AnalystOutput(
        generated_at=datetime.utcnow(),
        direction="bullish",
        confidence=0.75,
        primary_drivers=["USD weakness", "Real rates down"],
        counter_drivers=["Risk-on appetite"],
        narrative="Gold is supported by macro tailwinds.",
        key_events=["FOMC minutes", "CPI print"],
    )
    data = output.to_dict()

    assert data["direction"] == "bullish"
    assert data["confidence"] == 0.75
    assert len(data["primary_drivers"]) == 2


def test_trade_plan_to_dict():
    """TradePlan.to_dict() should produce a complete dict."""
    plan = TradePlan(
        generated_at=datetime.utcnow(),
        snapshot_id=42,
        stance="long",
        horizon_hours=4,
        confidence=0.65,
        entry_rule="Entry above $2340",
        stop_rule="Exit if below $2310",
        take_profit_rule="Exit at $2380",
        invalidation_rule="Break of $2300",
        risk_note="High vol regime.",
        why="Macro tailwinds support gold.",
        model_version="gpt-4o-mini",
        prompt_version="v1.0",
        strategy_version="v1.0",
        expected_return_pct=1.5,
    )
    data = plan.to_dict()

    assert data["stance"] == "long"
    assert data["snapshot_id"] == 42
    assert data["horizon_hours"] == 4
    assert "expected_return_pct" in data


def test_mock_provider_generate():
    """Mock provider should return a valid LLMResponse."""
    import asyncio

    async def _test():
        provider = MockLLMProvider()
        response = await provider.generate("Test prompt")
        return response

    response = asyncio.run(_test())

    assert isinstance(response, LLMResponse)
    assert response.model_used == "mock"
    assert "direction" in response.parsed


def test_llm_response_defaults():
    """LLMResponse should have sensible defaults."""
    resp = LLMResponse(raw_text="hello", parsed={"key": "val"}, model_used="test")
    assert resp.tokens_used is None
