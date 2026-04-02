"""Evaluation layer — evaluator, metrics, and reports."""
from app.evaluation.evaluator import Evaluator
from app.evaluation.metrics import (
    compute_direction_hit_rate,
    compute_avg_return,
    compute_stop_tp_rates,
    compute_all_metrics,
    AggregatedMetrics,
)
from app.evaluation.reports import generate_daily_report, generate_weekly_report

__all__ = [
    "Evaluator",
    "compute_direction_hit_rate",
    "compute_avg_return",
    "compute_stop_tp_rates",
    "compute_all_metrics",
    "AggregatedMetrics",
    "generate_daily_report",
    "generate_weekly_report",
]
