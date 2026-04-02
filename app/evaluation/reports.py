"""报表生成 — 日报和周报（中文输出）。"""
from datetime import datetime, timedelta
from app.db.models import Evaluation, Snapshot
from app.evaluation.metrics import compute_all_metrics, compute_direction_hit_rate


def generate_daily_report(
    evals: list[Evaluation],
    snapshots: dict[int, Snapshot],
    date: datetime | None = None,
) -> str:
    """生成 Markdown 格式日报（中文）。"""
    date = date or datetime.utcnow()
    date_str = date.strftime("%Y-%m-%d")

    lines = [
        f"# 日报 — {date_str}",
        "",
        f"**生成时间:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if not evals:
        lines.extend(["## 表现统计", "", "*该时段暂无评估数据。*", ""])
        return "\n".join(lines)

    metrics = compute_all_metrics(evals, snapshots)
    hit_rate = compute_direction_hit_rate(evals)

    lines.extend([
        "## 表现总览",
        "",
        f"- **评估数量:** {metrics['total_evaluated']}",
        f"- **方向准确率:** {hit_rate:.1%}",
        f"- **平均实际收益:** {metrics['avg_actual_return']:+.3f}%",
        f"- **止损触发率:** {metrics['stop_hit_rate']:.1%}",
        f"- **止盈触发率:** {metrics['tp_hit_rate']:.1%}",
        f"- **预期 vs 实际平均差值:** {metrics['avg_expected_vs_actual']:+.3f}%",
        "",
        "## 信号分类统计",
        "",
    ])

    by_stance: dict[str, list[Evaluation]] = {}
    for e in evals:
        snap = snapshots.get(e.snapshot_id)
        if not snap:
            continue
        plan = snap.trade_plan_json or {}
        stance = plan.get("stance", "unknown")
        by_stance.setdefault(stance, []).append(e)

    stance_labels = {"long": "做多", "short": "做空", "neutral": "观望", "unknown": "未知"}
    for stance, stance_evals in sorted(by_stance.items()):
        stance_hits = [e for e in stance_evals if e.direction_hit is True]
        stance_non_neutral = [e for e in stance_evals if e.direction_hit is not None]
        rate = len(stance_hits) / len(stance_non_neutral) if stance_non_neutral else 0.0
        label = stance_labels.get(stance, stance)
        lines.append(
            f"- **{label.upper()}** ({len(stance_evals)} 个信号): 准确率 {rate:.1%}"
        )

    lines.append("")
    return "\n".join(lines)


def generate_weekly_report(
    evals: list[Evaluation],
    snapshots: dict[int, Snapshot],
    week_of: datetime | None = None,
) -> str:
    """生成 Markdown 格式周报（中文）。"""
    week_of = week_of or datetime.utcnow()
    start_of_week = week_of - timedelta(days=week_of.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    lines = [
        f"# 周报 — {start_of_week.strftime('%Y-%m-%d')} 至 {end_of_week.strftime('%Y-%m-%d')}",
        "",
        f"**生成时间:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if not evals:
        lines.extend(["## 本周表现", "", "*本周暂无评估数据。*", ""])
        return "\n".join(lines)

    metrics = compute_all_metrics(evals, snapshots)
    hit_rate = compute_direction_hit_rate(evals)

    lines.extend([
        "## 本周表现总览",
        "",
        f"- **评估数量:** {metrics['total_evaluated']}",
        f"- **方向准确率:** {hit_rate:.1%}",
        f"- **平均实际收益:** {metrics['avg_actual_return']:+.3f}%",
        f"- **止损触发率:** {metrics['stop_hit_rate']:.1%}",
        f"- **止盈触发率:** {metrics['tp_hit_rate']:.1%}",
        "",
        "## 每日明细",
        "",
        "| 日期 | 评估数 | 准确率 | 平均收益 |",
        "|------|--------|--------|--------|",
    ])

    by_date: dict[str, list[Evaluation]] = {}
    for e in evals:
        date_key = e.evaluated_at.strftime("%Y-%m-%d")
        by_date.setdefault(date_key, []).append(e)

    for date_key in sorted(by_date.keys()):
        date_evals = by_date[date_key]
        date_hits = [ev for ev in date_evals if ev.direction_hit is True]
        date_non_neutral = [ev for ev in date_evals if ev.direction_hit is not None]
        rate = len(date_hits) / len(date_non_neutral) if date_non_neutral else 0.0
        avg_ret = sum(ev.actual_return or 0 for ev in date_evals) / len(date_evals)
        lines.append(f"| {date_key} | {len(date_evals)} | {rate:.1%} | {avg_ret:+.3f}% |")

    lines.append("")
    return "\n".join(lines)
