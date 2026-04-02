#!/usr/bin/env python3
"""定时汇报脚本 — 检查最新评估结果并输出简报。"""
from datetime import datetime, timedelta, UTC
from sqlalchemy import select, func
from app.db.session import get_session_factory
from app.db.models import Snapshot, Evaluation


def get_stats(session):
    """获取评估统计。"""
    total_snapshots = session.scalar(select(func.count(Snapshot.id))) or 0

    # 所有已评估的快照（含 neutral 立场）
    all_evaluated = session.scalar(select(func.count(Evaluation.id))) or 0

    # 有方向预测的快照（long/short，非 neutral）
    directional = session.scalar(
        select(func.count(Evaluation.id))
        .where(Evaluation.direction_hit.isnot(None))
    ) or 0

    # 方向命中数
    direction_hits = session.scalar(
        select(func.count(Evaluation.id))
        .where(Evaluation.direction_hit == True)
    ) or 0

    # 准确率只算有方向预测的快照
    accuracy = (direction_hits / directional * 100) if directional else None

    last_eval = session.scalar(
        select(Evaluation).order_by(Evaluation.evaluated_at.desc()).limit(1)
    )

    week_ago = datetime.now(UTC) - timedelta(days=7)
    recent = session.scalar(
        select(func.count(Snapshot.id))
        .where(Snapshot.created_at >= week_ago)
    ) or 0

    return {
        "total_snapshots": total_snapshots,
        "all_evaluated": all_evaluated,
        "directional": directional,
        "direction_hits": direction_hits,
        "accuracy": accuracy,
        "last_eval": last_eval,
        "recent_7d": recent,
    }


def format_report():
    session = get_session_factory()()
    try:
        stats = get_stats(session)
    finally:
        session.close()

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 **Gold Trader 定时汇报** — {now}",
        f"",
        f"**快照总数：** {stats['total_snapshots']} | **近7天：** {stats['recent_7d']}",
        f"**已评估：** {stats['all_evaluated']} 条（含 neutral {stats['all_evaluated'] - stats['directional']} 条）",
    ]

    if stats['accuracy'] is not None:
        lines.append(f"**方向准确率：** {stats['accuracy']:.1f}% ({stats['direction_hits']}/{stats['directional']})")
    else:
        lines.append(f"**方向准确率：** 暂无方向预测数据")

    if stats['last_eval']:
        ev = stats['last_eval']
        actual = f"{ev.actual_return:+.3f}%" if ev.actual_return is not None else "N/A"
        hit_str = "✅" if ev.direction_hit == True else ("❌" if ev.direction_hit == False else "—")
        lines.append(f"**最新评估：** 快照#{ev.snapshot_id} | 方向={ev.direction_actual} | 命中={hit_str} | 止盈/止损={ev.stop_hit} | 实际={actual}")

    lines.append(f"")
    lines.append(f"调度器状态：每4小时运行一次（session: sharp-cloud）")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report())
