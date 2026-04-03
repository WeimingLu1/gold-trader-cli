"""Backtest performance metrics."""
from collections import defaultdict
from datetime import date
from app.backtest.models import BacktestSnapshot, BacktestEvaluation


def compute_metrics(
    snapshots: list[BacktestSnapshot],
    evaluations: list[BacktestEvaluation],
) -> dict:
    """
    Compute aggregate performance metrics from backtest snapshots and evaluations.

    Returns:
        dict with keys:
          - total_snapshots, evaluated_snapshots
          - direction_hit_rate: fraction where predicted direction matched actual
          - stop_hit_rate, tp_hit_rate, neither_rate
          - avg_actual_return, avg_expected_return
          - win_rate (actual_return > 0 for long, < 0 for short)
          - sharpe_ratio: annualized Sharpe of returns
          - max_drawdown: maximum peak-to-trough drawdown
          - by_stance: {stance: {count, hit_rate, avg_return}}
          - by_month: {YYYY-MM: {count, hit_rate, pnl}}
    """
    evals_by_snap = {e.backtest_snapshot_id: e for e in evaluations}
    directional = [e for e in evaluations if e.direction_hit is not None]
    directional_long = [e for e in directional if e.snapshot.stance == "long"]
    directional_short = [e for e in directional if e.snapshot.stance == "short"]

    # Direction hit rate overall
    direction_hit_rate = (
        sum(1 for e in directional if e.direction_hit) / len(directional)
        if directional
        else 0.0
    )

    # By stance
    by_stance = {}
    for stance in ("long", "short", "neutral"):
        st_evals = [e for e in directional if e.snapshot.stance == stance]
        hit_rate = (
            sum(1 for e in st_evals if e.direction_hit) / len(st_evals)
            if st_evals
            else 0.0
        )
        avg_ret = (
            sum(e.actual_return for e in st_evals) / len(st_evals)
            if st_evals
            else 0.0
        )
        by_stance[stance] = {
            "count": len(st_evals),
            "hit_rate": round(hit_rate, 4),
            "avg_return": round(avg_ret, 4),
        }

    # Win rate
    long_wins = sum(1 for e in directional_long if e.actual_return and e.actual_return > 0)
    short_wins = sum(1 for e in directional_short if e.actual_return and e.actual_return < 0)
    win_rate_long = long_wins / len(directional_long) if directional_long else 0.0
    win_rate_short = short_wins / len(directional_short) if directional_short else 0.0

    # Stop/TP rates — based on directional evaluations only
    n_dir = len(directional) or 1
    stop_hits = sum(1 for e in directional if e.stop_hit == "stop")
    tp_hits = sum(1 for e in directional if e.stop_hit == "tp")
    neither = sum(1 for e in directional if e.stop_hit == "neither")

    # Return metrics — directional snapshots only (neutral has no position, actual_return=0)
    dir_returns = [e.actual_return for e in directional if e.actual_return is not None]
    if len(dir_returns) >= 2:
        mean_ret = sum(dir_returns) / len(dir_returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in dir_returns) / (len(dir_returns) - 1)) ** 0.5
        # Annualize: ~6.5 4h periods per day, ~252 trading days
        periods_per_year = 6.5 * 252
        sharpe = (mean_ret / std_ret) * (periods_per_year ** 0.5) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown on directional equity curve
    max_dd = 0.0
    peak = 0.0
    cumulative = 0.0
    for r in dir_returns:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Monthly breakdown
    # accuracy uses directional count (excluding neutral stances)
    # pnl is the sum of actual_return % per snapshot (non-compounded)
    monthly: dict[str, dict] = defaultdict(lambda: {"count": 0, "wins": 0, "directional_count": 0, "pnl": 0.0})
    for e in evaluations:
        if e.actual_return is None:
            continue
        d: date = e.snapshot.as_of.date()
        key = d.strftime("%Y-%m")
        monthly[key]["count"] += 1
        monthly[key]["pnl"] += e.actual_return or 0
        if e.direction_hit is not None:
            monthly[key]["directional_count"] += 1
            if e.direction_hit:
                monthly[key]["wins"] += 1

    monthly_summary = {}
    for month, stats in sorted(monthly.items()):
        hit = stats["wins"] / stats["directional_count"] if stats["directional_count"] else 0
        monthly_summary[month] = {
            "count": stats["count"],
            "directional_count": stats["directional_count"],
            "hit_rate": round(hit, 4),
            "pnl": round(stats["pnl"], 4),
        }

    # Avg expected vs actual — directional snapshots only
    evals_w_exp = [e for e in directional if e.expected_return is not None]
    avg_expected = (
        sum(e.expected_return for e in evals_w_exp) / len(evals_w_exp) if evals_w_exp else 0
    )
    avg_actual = sum(dir_returns) / len(dir_returns) if dir_returns else 0

    return {
        "total_snapshots": len(snapshots),
        "evaluated_snapshots": len(evaluations),
        "direction_hit_rate": round(direction_hit_rate, 4),
        "win_rate_long": round(win_rate_long, 4),
        "win_rate_short": round(win_rate_short, 4),
        "stop_hit_rate": round(stop_hits / n_dir, 4),
        "tp_hit_rate": round(tp_hits / n_dir, 4),
        "neither_rate": round(neither / n_dir, 4),
        "avg_expected_return": round(avg_expected, 4),
        "avg_actual_return": round(avg_actual, 4),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 4),
        "by_stance": by_stance,
        "by_month": monthly_summary,
    }
