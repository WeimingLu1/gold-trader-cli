"""Tests for the evaluation layer."""
from datetime import datetime
from app.evaluation.evaluator import Evaluator


def _make_snapshot(stance: str = "neutral", xau_price: float = 2345.0):
    """Helper to create a minimal Snapshot-like object for evaluator testing."""
    stop_price = round(xau_price * 0.985, 2)
    tp_price = round(xau_price * 1.015, 2)

    class FakeSnapshot:
        pass

    snap = FakeSnapshot()
    snap.id = 1
    snap.xau_price = xau_price
    snap.horizon_hours = 4
    snap.trade_plan_json = {
        "stance": stance,
        "stop_rule": f"Exit if price falls below ${stop_price:.2f}",
        "take_profit_rule": f"Exit if price reaches ${tp_price:.2f}",
        "expected_return_pct": 1.5,
    }
    snap.prompt_version = "test"
    snap.model_version = "mock"
    snap.strategy_version = "test"
    return snap


def test_evaluator_long_wins():
    """Long stance, price goes up → direction hit."""
    evaluator = Evaluator()
    snap = _make_snapshot(stance="long", xau_price=2345.0)
    current_price = 2355.0  # price went up

    eval_result = evaluator.evaluate(snap, current_price)

    assert eval_result.direction_actual == "up"
    assert eval_result.direction_hit is True


def test_evaluator_long_loses():
    """Long stance, price goes down → direction miss."""
    evaluator = Evaluator()
    snap = _make_snapshot(stance="long", xau_price=2345.0)
    current_price = 2335.0  # price went down

    eval_result = evaluator.evaluate(snap, current_price)

    assert eval_result.direction_actual == "down"
    assert eval_result.direction_hit is False


def test_evaluator_neutral_no_hit():
    """Neutral stance → direction_hit is None."""
    evaluator = Evaluator()
    snap = _make_snapshot(stance="neutral", xau_price=2345.0)
    current_price = 2355.0

    eval_result = evaluator.evaluate(snap, current_price)

    assert eval_result.direction_hit is None
    assert eval_result.actual_return > 0


def test_evaluator_short_wins():
    """Short stance, price goes down → direction hit."""
    evaluator = Evaluator()
    snap = _make_snapshot(stance="short", xau_price=2345.0)
    current_price = 2335.0

    eval_result = evaluator.evaluate(snap, current_price)

    assert eval_result.direction_actual == "down"
    assert eval_result.direction_hit is True


def test_evaluator_flat_price():
    """Price barely changed → flat."""
    evaluator = Evaluator()
    snap = _make_snapshot(stance="long", xau_price=2345.0)
    current_price = 2345.5  # tiny move

    eval_result = evaluator.evaluate(snap, current_price)

    assert eval_result.direction_actual == "flat"
    assert eval_result.direction_hit is False
