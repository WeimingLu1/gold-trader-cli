"""Metrics computation from evaluation records."""
from typing import TypedDict
from app.db.models import Evaluation, Snapshot


class AggregatedMetrics(TypedDict):
    total_evaluated: int
    direction_hit_rate: float
    avg_actual_return: float
    stop_hit_rate: float
    tp_hit_rate: float
    avg_expected_vs_actual: float


def compute_direction_hit_rate(evals: list[Evaluation]) -> float:
    """Direction hit rate among non-neutral predictions."""
    non_neutral = [e for e in evals if e.direction_hit is not None]
    if not non_neutral:
        return 0.0
    hits = sum(1 for e in non_neutral if e.direction_hit)
    return round(hits / len(non_neutral), 4)


def compute_avg_return(evals: list[Evaluation]) -> float:
    """Average actual return % across all evaluated snapshots."""
    with_return = [e.actual_return for e in evals if e.actual_return is not None]
    if not with_return:
        return 0.0
    return round(sum(with_return) / len(with_return), 4)


def compute_stop_tp_rates(evals: list[Evaluation]) -> tuple[float, float, float]:
    """Return (stop_rate, tp_rate, neither_rate) among directional predictions."""
    directional = [e for e in evals if e.stop_hit is not None and e.stop_hit != "pending"]
    if not directional:
        return 0.0, 0.0, 0.0
    stops = sum(1 for e in directional if e.stop_hit == "stop")
    tps = sum(1 for e in directional if e.stop_hit == "tp")
    neithers = sum(1 for e in directional if e.stop_hit == "neither")
    n = len(directional)
    return round(stops / n, 4), round(tps / n, 4), round(neithers / n, 4)


def compute_avg_expected_vs_actual(evals: list[Evaluation]) -> float:
    """Average gap between expected and actual return."""
    paired = [
        e.actual_return - e.expected_return
        for e in evals
        if e.actual_return is not None and e.expected_return is not None
    ]
    if not paired:
        return 0.0
    return round(sum(paired) / len(paired), 4)


def group_by_confidence_bucket(
    evals: list[Evaluation], snapshots: dict[int, Snapshot]
) -> dict[str, float]:
    """
    Group direction hit rates by analyst confidence bucket.

    Bucket: high (≥0.7), medium (0.4-0.7), low (<0.4)
    """
    buckets: dict[str, list] = {"high": [], "medium": [], "low": []}

    for e in evals:
        if e.direction_hit is None:
            continue
        snap = snapshots.get(e.snapshot_id)
        if not snap:
            continue
        analyst_output = snap.analyst_output_json or {}
        confidence = analyst_output.get("confidence", 0.5)

        if confidence >= 0.7:
            buckets["high"].append(e.direction_hit)
        elif confidence >= 0.4:
            buckets["medium"].append(e.direction_hit)
        else:
            buckets["low"].append(e.direction_hit)

    return {
        bucket: round(sum(hits) / len(hits), 4) if hits else 0.0
        for bucket, hits in buckets.items()
    }


def compute_all_metrics(evals: list[Evaluation], snapshots: dict[int, Snapshot]) -> AggregatedMetrics:
    """Compute all metrics in one pass."""
    stop_rate, tp_rate, neither_rate = compute_stop_tp_rates(evals)
    return AggregatedMetrics(
        total_evaluated=len(evals),
        direction_hit_rate=compute_direction_hit_rate(evals),
        avg_actual_return=compute_avg_return(evals),
        stop_hit_rate=stop_rate,
        tp_hit_rate=tp_rate,
        avg_expected_vs_actual=compute_avg_expected_vs_actual(evals),
    )
