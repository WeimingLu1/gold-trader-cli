"""Backtest performance metrics."""
from collections import defaultdict
from datetime import date
from app.backtest.models import BacktestSnapshot, BacktestEvaluation


def compute_metrics(
    snapshots: list[BacktestSnapshot],
    evaluations: list[BacktestEvaluation],
    initial_capital: float = 100_000.0,
    position_fraction: float = 0.10,
) -> dict:
    """
    Compute aggregate performance metrics from backtest snapshots and evaluations.

    Returns:
        dict with keys:
          - total_snapshots, evaluated_snapshots
          - direction_hit_rate: fraction where predicted direction matched actual
          - stop_hit_rate, tp_hit_rate, neither_rate
          - avg_actual_return, avg_expected_return (portfolio return % per trade)
          - win_rate (actual_return > 0 for long, < 0 for short)
          - sharpe_ratio: annualized Sharpe of returns
          - max_drawdown_pct: maximum peak-to-trough drawdown %
          - final_equity, total_return_pct, initial_capital
          - by_stance: {stance: {count, hit_rate, avg_return}}
          - by_month: {YYYY-MM: {count, directional_count, hit_rate, pnl_dollars}}
    """
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

    # Win rate — portfolio return % > 0 means profitable trade
    long_wins = sum(1 for e in directional_long if e.pnl_pct is not None and e.pnl_pct > 0)
    short_wins = sum(1 for e in directional_short if e.pnl_pct is not None and e.pnl_pct > 0)
    win_rate_long = long_wins / len(directional_long) if directional_long else 0.0
    win_rate_short = short_wins / len(directional_short) if directional_short else 0.0

    # Stop/TP rates — directional only
    n_dir = len(directional) or 1
    stop_hits = sum(1 for e in directional if e.stop_hit == "stop")
    tp_hits = sum(1 for e in directional if e.stop_hit == "tp")
    neither = sum(1 for e in directional if e.stop_hit == "neither")

    # Equity curve with compound returns
    equity = initial_capital
    equity_curve = []
    for e in evaluations:
        if e.pnl_pct is not None:
            equity *= (1 + e.pnl_pct / 100)
        equity_curve.append(equity)

    final_equity = equity_curve[-1] if equity_curve else initial_capital
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    # Sharpe & max drawdown from compound equity series
    all_pnl = [e.pnl_pct for e in evaluations if e.pnl_pct is not None]
    if len(all_pnl) >= 2:
        mean_ret = sum(all_pnl) / len(all_pnl)
        std_ret = (sum((r - mean_ret) ** 2 for r in all_pnl) / (len(all_pnl) - 1)) ** 0.5
        periods_per_year = 6.5 * 252
        sharpe = (mean_ret / std_ret) * (periods_per_year ** 0.5) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    peak = initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = max_dd * 100

    # Monthly breakdown — equity compounds per snapshot; monthly P&L = equity_end - equity_start
    monthly: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "wins": 0, "directional_count": 0, "equity_start": initial_capital, "equity_end": initial_capital}
    )
    month_equity = initial_capital
    prev_month = None
    for e in evaluations:
        d: date = e.snapshot.as_of.date()
        key = d.strftime("%Y-%m")
        if key != prev_month:
            monthly[key]["equity_start"] = month_equity
            prev_month = key
        monthly[key]["count"] += 1
        if e.direction_hit is not None:
            monthly[key]["directional_count"] += 1
            if e.direction_hit:
                monthly[key]["wins"] += 1
        if e.pnl_pct is not None:
            month_equity *= (1 + e.pnl_pct / 100)
        monthly[key]["equity_end"] = month_equity

    monthly_summary = {}
    for month, stats in sorted(monthly.items()):
        hit = stats["wins"] / stats["directional_count"] if stats["directional_count"] else 0
        monthly_summary[month] = {
            "count": stats["count"],
            "directional_count": stats["directional_count"],
            "hit_rate": round(hit, 4),
            "pnl_dollars": round(stats["equity_end"] - stats["equity_start"], 2),
        }

    # Avg expected vs actual — per-directional-trade, portfolio return %
    evals_w_exp = [e for e in directional if e.expected_return is not None]
    avg_expected = (
        sum(e.expected_return * position_fraction for e in evals_w_exp) / len(evals_w_exp) if evals_w_exp else 0
    )
    avg_actual = sum(all_pnl) / len(all_pnl) if all_pnl else 0
    # Per-directional-trade average (neutral=0 dilutes the average)
    directional_pnl = [e.pnl_pct for e in directional if e.pnl_pct is not None]
    avg_actual_dir = sum(directional_pnl) / len(directional_pnl) if directional_pnl else 0

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
        "avg_actual_return": round(avg_actual_dir, 4),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 4),
        "initial_capital": initial_capital,
        "by_stance": by_stance,
        "by_month": monthly_summary,
    }
