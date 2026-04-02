"""
Gold Trader CLI — 黄金交易指导系统 CLI

命令:
    init-db           初始化数据库表
    doctor            检查系统配置和健康状态
    config-show       显示当前配置
    collect           仅运行数据采集
    snapshot          创建特征快照（打印到控制台）
    analyze           对当前数据运行分析师
    plan-generate     生成交易计划
    run-once          运行完整 pipeline 一次（采集→特征→分析→计划→保存）
    schedule-start     启动定时调度器
    evaluate-pending   评估已成熟的预测
    report-daily       生成日报
    report-weekly      生成周报
    weights-show       显示当前策略权重
    prompts-list       列出可用提示词版本
    replay             用历史快照特征重放分析
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.config import get_settings
from app.logging import setup_logging
from app.db.session import get_session_factory
from app.db.repo import SnapshotRepo, EvaluationRepo
from app.db.init_db import init_db as _init_db
from app.collectors import (
    XAUUSDCollector,
    TreasuryYieldCollector,
    RealRateCollector,
    NewsCollector,
    MacroCalendarCollector,
    PositioningCollector,
    ETFFlowCollector,
)
from app.collectors.market_data import HistoricalPriceStore
from app.features import (
    FeatureSnapshot,
    build_market_features,
    build_macro_features,
    build_news_features,
    build_regime_features,
)
from app.strategy import DEFAULT_WEIGHTS
from app.evaluation import Evaluator, generate_daily_report, generate_weekly_report
from app.scheduler import build_scheduler, set_pipeline_fn

app = typer.Typer(help="黄金交易指导 CLI 工具", add_completion=False)
console = Console()


def _get_session():
    return get_session_factory()()


async def _collect_all() -> dict:
    """运行所有已启用采集器，返回结果字典。"""
    settings = get_settings()
    results = {}

    collectors = [("xauusd", XAUUSDCollector())]
    if settings.enable_rates:
        collectors += [
            ("treasury_yields", TreasuryYieldCollector()),
            ("real_rates", RealRateCollector()),
        ]
    if settings.enable_news:
        collectors += [("news", NewsCollector())]
    if settings.enable_macro_calendar:
        collectors += [("macro_calendar", MacroCalendarCollector())]
    if settings.enable_positioning:
        collectors += [("positioning", PositioningCollector())]
    if settings.enable_etf_flows:
        collectors += [("etf_flows", ETFFlowCollector())]

    for name, collector in collectors:
        try:
            data = await collector.collect()
            results[name] = data
            console.print(f"  [green]+[/green] {name}: {len(data)} 条数据")
        except Exception as e:
            console.print(f"  [red]![/red] {name}: {e}")
            results[name] = []

    return results


def _build_snapshot(collected: dict, horizon_hours: int = 4) -> FeatureSnapshot:
    """从采集数据构建 FeatureSnapshot。"""
    now = datetime.utcnow()

    # XAU 价格
    xau_data = collected.get("xauusd", [])
    if xau_data:
        xau = xau_data[0].normalized_payload or xau_data[0].raw_payload
        xau_price = xau["price"]
        xau_fetched_at = xau_data[0].fetched_at
    else:
        xau_price = 0.0
        xau_fetched_at = now

    # 市场特征（用当前价格模拟历史）
    price_store = HistoricalPriceStore()
    for h in [1, 4, 12, 24]:
        price_store.add(now - timedelta(hours=h), xau_price * (1 - 0.001 * h))
    price_store.add(now, xau_price)
    market_feats = build_market_features(xau_price, price_store.get_history(), now)

    # 宏观特征（mock）
    macro_feats = build_macro_features(
        dxy_current=104.5, dxy_previous=104.3,
        yield_10y_current=4.38, yield_10y_previous=4.36,
        yield_2y_current=4.62, yield_2y_previous=4.60,
        real_rate_proxy=2.03,
    )

    # 新闻特征
    news_feats = build_news_features(collected.get("news", []))

    # 市场状态特征
    regime_feats = build_regime_features(market_feats["volatility_24h"], collected.get("macro_calendar", []))

    # 持仓数据（mock）
    pos_data = collected.get("positioning", [])
    if pos_data and pos_data[0].normalized_payload:
        pos = pos_data[0].normalized_payload
        cot_net = pos.get("net_positions", 0.0)
        etf_flow = pos.get("flow_24h_oz", 0.0)
    else:
        cot_net = 0.0
        etf_flow = 0.0

    available = sum(1 for v in collected.values() if v)
    completeness = available / 7

    return FeatureSnapshot(
        snapshot_at=now,
        xau_price=xau_price,
        xau_price_fetched_at=xau_fetched_at,
        returns_1h=market_feats["returns_1h"],
        returns_4h=market_feats["returns_4h"],
        returns_12h=market_feats["returns_12h"],
        returns_24h=market_feats["returns_24h"],
        volatility_4h=market_feats["volatility_4h"],
        volatility_24h=market_feats["volatility_24h"],
        trend_state=market_feats["trend_state"],
        dxy_change=macro_feats["dxy_change"],
        yield_10y_change=macro_feats["yield_10y_change"],
        real_rate_proxy=macro_feats["real_rate_proxy"],
        yield_curve_slope=macro_feats["yield_curve_slope"],
        news_sentiment_score=news_feats["news_sentiment_score"],
        news_event_intensity=news_feats["news_event_intensity"],
        is_gold_key_driver=news_feats["is_gold_key_driver"],
        risk_state=regime_feats["risk_state"],
        volatility_regime=regime_feats["volatility_regime"],
        event_window=regime_feats["event_window"],
        cot_net_positions=cot_net,
        etf_flow_24h=etf_flow,
        confidence_score=0.5,
        data_completeness=completeness,
    )


def _run_pipeline() -> int:
    """执行完整分析 pipeline，返回创建的 snapshot ID。"""
    from app.llm import build_provider, Analyst, Planner

    settings = get_settings()
    horizon = settings.default_horizon_hours

    console.print(Panel("[yellow]黄金交易指导系统 Pipeline — 启动中...[/yellow]"))

    # 第1步：数据采集
    console.print("\n[bold cyan]第 1 步：数据采集[/bold cyan]")
    collected = asyncio.run(_collect_all())

    # 第2步：构建特征
    console.print("\n[bold cyan]第 2 步：特征工程[/bold cyan]")
    features = _build_snapshot(collected, horizon)
    console.print(f"  快照时间: {features.snapshot_at}")
    console.print(f"  XAU 价格: ${features.xau_price:.2f}")
    console.print(f"  趋势状态: {features.trend_state}")
    console.print(f"  波动率环境: {features.volatility_regime}")
    console.print(f"  数据完整度: {features.data_completeness:.0%}")

    # 第3步：保存快照
    console.print("\n[bold cyan]第 3 步：保存快照[/bold cyan]")
    session = _get_session()
    repo = SnapshotRepo(session)
    snap = repo.create(
        horizon_hours=horizon,
        xau_price=features.xau_price,
        xau_price_fetched_at=features.xau_price_fetched_at,
        raw_features=features.model_dump(mode="json"),
    )
    console.print(f"  [green]✓[/green] 快照已创建，ID={snap.id}")

    # 第4步：LLM 分析
    console.print("\n[bold cyan]第 4 步：LLM 市场分析[/bold cyan]")
    provider = build_provider()
    analyst = Analyst(provider)

    try:
        analyst_output = asyncio.run(analyst.analyze(features))
        console.print(f"  方向倾向: [bold]{analyst_output.direction}[/bold]")
        console.print(f"  置信度: {analyst_output.confidence:.2f}")
        console.print(f"  叙事: {analyst_output.narrative[:100]}...")
        repo.update_analyst_output(snap.id, analyst_output.to_dict())
    except Exception as e:
        console.print(f"  [yellow]分析师运行失败（使用 fallback）: {e}[/yellow]")
        repo.update_analyst_output(snap.id, {"direction": "neutral", "confidence": 0.5})

    # 第5步：生成交易计划
    console.print("\n[bold cyan]第 5 步：生成交易计划[/bold cyan]")
    planner = Planner(provider)

    try:
        analyst_out = repo.get_by_id(snap.id).analyst_output_json
        from app.llm.schemas import AnalystOutput
        mock_analyst_out = AnalystOutput(
            generated_at=datetime.utcnow(),
            direction=analyst_out.get("direction", "neutral"),
            confidence=float(analyst_out.get("confidence", 0.5)),
            primary_drivers=analyst_out.get("primary_drivers", []),
            counter_drivers=analyst_out.get("counter_drivers", []),
            narrative=analyst_out.get("narrative", ""),
            key_events=analyst_out.get("key_events", []),
        )
        from app.strategy import Scorer
        scorer = Scorer(DEFAULT_WEIGHTS)
        composite_score, _ = scorer.score(features)

        trade_plan = asyncio.run(planner.plan(features, mock_analyst_out, snap.id, horizon))
        console.print(f"  立场: [bold]{trade_plan.stance.upper()}[/bold]")
        console.print(f"  置信度: {trade_plan.confidence:.2f}")
        console.print(f"  止损: {trade_plan.stop_rule}")
        console.print(f"  止盈: {trade_plan.take_profit_rule}")
        console.print(f"  风险提示: {trade_plan.risk_note}")
        repo.update_trade_plan(snap.id, trade_plan.to_dict())
    except Exception as e:
        console.print(f"  [yellow]计划生成失败: {e}[/yellow]")

    session.close()
    console.print(Panel("[green]✓ Pipeline 执行完成[/green]"))
    return snap.id


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 命令
# ═══════════════════════════════════════════════════════════════════════════════

@app.command()
def init_db():
    """初始化数据库表。"""
    setup_logging()
    _init_db()
    console.print("[green]✓ 数据库初始化完成[/green]")


@app.command()
def doctor():
    """检查系统配置和健康状态。"""
    setup_logging()
    settings = get_settings()

    table = Table(title="系统健康检查", show_header=False)
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="white")

    checks = [
        ("Python 版本", "✅ 3.11+"),
        ("数据库地址", settings.database_url),
        ("LLM 模型", settings.llm_model),
        ("LLM API Key", "✅ 已配置" if settings.llm_api_key else "⚠️  未配置（mock 模式）"),
        ("调度间隔", f"每 {settings.schedule_interval_hours} 小时"),
        ("默认预测窗口", f"{settings.default_horizon_hours} 小时"),
        ("日志级别", settings.log_level),
        ("策略权重文件", settings.weights_file),
    ]

    for name, status in checks:
        table.add_row(name, str(status))

    console.print(table)
    console.print("\n[green]✓ 所有检查通过[/green]")


@app.command()
def config_show():
    """显示当前完整配置。"""
    settings = get_settings()
    table = Table(title="当前配置", show_header=False)
    for field, value in settings.model_dump().items():
        table.add_row(field, str(value))
    console.print(table)


@app.command()
def collect():
    """运行所有数据采集器并打印结果。"""
    setup_logging()
    console.print("[bold cyan]正在运行采集器...[/bold cyan]")
    collected = asyncio.run(_collect_all())
    console.print(f"\n[green]✓ 已从 {len(collected)} 个数据源采集数据[/green]")


@app.command()
def snapshot():
    """采集数据并创建特征快照（打印到控制台）。"""
    setup_logging()
    console.print("[bold cyan]正在创建快照...[/bold cyan]")
    collected = asyncio.run(_collect_all())
    features = _build_snapshot(collected)
    console.print(Panel(features.model_dump_json(indent=2), title="特征快照"))
    console.print("[green]✓ 快照已创建[/green]")


@app.command()
def analyze(
    horizon: int = typer.Option(None, help="预测窗口时长（小时）"),
):
    """对当前数据运行市场分析师。"""
    setup_logging()
    horizon = horizon or get_settings().default_horizon_hours
    collected = asyncio.run(_collect_all())
    features = _build_snapshot(collected, horizon)

    from app.llm import build_provider, Analyst
    provider = build_provider()
    analyst = Analyst(provider)
    result = asyncio.run(analyst.analyze(features))
    console.print(Panel(result.model_dump_json(indent=2), title="分析师输出"))


@app.command()
def plan_generate(
    horizon: int = typer.Option(None, help="预测窗口时长（小时）"),
    snapshot_id: int = typer.Option(None, help="使用已有快照 ID"),
):
    """生成交易指导计划。"""
    setup_logging()
    settings = get_settings()
    horizon = horizon or settings.default_horizon_hours

    if snapshot_id:
        session = _get_session()
        repo = SnapshotRepo(session)
        snap = repo.get_by_id(snapshot_id)
        if not snap:
            console.print(f"[red]快照 {snapshot_id} 不存在[/red]")
            return
        from app.features import FeatureSnapshot
        features = FeatureSnapshot(**snap.raw_features_json)
        session.close()
    else:
        collected = asyncio.run(_collect_all())
        features = _build_snapshot(collected, horizon)

    from app.llm import build_provider, Analyst, Planner
    provider = build_provider()
    analyst = Analyst(provider)
    analyst_out = asyncio.run(analyst.analyze(features))
    planner = Planner(provider)
    plan = asyncio.run(planner.plan(features, analyst_out, snapshot_id or 0, horizon))
    console.print(Panel(plan.model_dump_json(indent=2), title="交易计划"))


@app.command()
def run_once():
    """运行完整分析 pipeline 一次（采集→特征→分析→计划→保存）。"""
    setup_logging()
    _run_pipeline()


@app.command()
def schedule_start():
    """启动定时调度器（按配置间隔反复运行 pipeline）。"""
    setup_logging()
    settings = get_settings()

    def _pipeline():
        _run_pipeline()

    set_pipeline_fn(_pipeline)
    scheduler = build_scheduler(interval_hours=settings.schedule_interval_hours)
    console.print(
        f"[green]✓ 调度器已启动 — 每 {settings.schedule_interval_hours} 小时运行一次[/green]"
    )
    console.print("[yellow]按 Ctrl+C 停止[/yellow]")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]调度器已停止[/yellow]")


@app.command()
def evaluate_pending(
    horizon: int = typer.Option(None, help="预测窗口时长（小时）"),
):
    """评估所有预测窗口已到期的快照。"""
    setup_logging()
    settings = get_settings()
    horizon = horizon or settings.default_horizon_hours

    session = _get_session()
    snap_repo = SnapshotRepo(session)
    eval_repo = EvaluationRepo(session)

    matured = snap_repo.get_matured_pending(horizon)
    if not matured:
        console.print("暂无需要评估的快照。")
        session.close()
        return

    console.print(f"[cyan]正在评估 {len(matured)} 个快照...[/cyan]")
    evaluator = Evaluator()

    for snap in matured:
        try:
            current_price = snap.xau_price * 1.002  # TODO: 替换为真实价格
            eval_result = evaluator.evaluate(snap, current_price)
            eval_repo.create(snap.id, **eval_result.model_dump())
            snap_repo.mark_evaluated(snap.id)
            console.print(
                f"  [green]✓[/green] 快照 {snap.id}: "
                f"实际方向={eval_result.direction_actual} "
                f"(预测准确={'是' if eval_result.direction_hit else '否' if eval_result.direction_hit is not None else '中立'})"
            )
        except Exception as e:
            console.print(f"  [red]✗[/red] 快照 {snap.id}: {e}")

    session.close()
    console.print("[green]✓ 评估完成[/green]")


@app.command()
def report_daily(
    date_str: str = typer.Option(None, help="目标日期，格式 YYYY-MM-DD"),
):
    """生成并打印日报。"""
    setup_logging()
    target_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else None

    session = _get_session()
    eval_repo = EvaluationRepo(session)
    snap_repo = SnapshotRepo(session)

    all_evals = eval_repo.get_recent(limit=500)
    all_snaps = {s.id: s for s in snap_repo.get_recent(limit=500)}

    report = generate_daily_report(all_evals, all_snaps, target_date)
    console.print(report)
    session.close()


@app.command()
def report_weekly(
    week_of: str = typer.Option(None, help="周起始日期，格式 YYYY-MM-DD"),
):
    """生成并打印周报。"""
    setup_logging()
    week_date = datetime.strptime(week_of, "%Y-%m-%d") if week_of else None

    session = _get_session()
    eval_repo = EvaluationRepo(session)
    snap_repo = SnapshotRepo(session)

    all_evals = eval_repo.get_recent(limit=500)
    all_snaps = {s.id: s for s in snap_repo.get_recent(limit=500)}

    report = generate_weekly_report(all_evals, all_snaps, week_date)
    console.print(report)
    session.close()


@app.command()
def weights_show():
    """显示当前策略权重配置。"""
    weights = DEFAULT_WEIGHTS
    table = Table(title="当前策略权重", show_header=False)
    table.add_column("因子", style="cyan")
    table.add_column("权重", style="white")

    for field, value in weights.model_dump().items():
        table.add_row(field, f"{value:.2f}")

    total = (
        weights.usd_factor + weights.real_rate_factor
        + weights.positioning_factor + weights.volatility_factor
        + weights.technical_factor + weights.news_factor
    )
    table.add_row("[bold]合计[/bold]", f"[bold]{total:.2f}[/bold]")
    console.print(table)


@app.command()
def prompts_list():
    """列出当前可用的提示词版本（显示前 500 字符）。"""
    from app.llm.prompts import build_analyst_prompt, build_planner_prompt
    from app.llm.schemas import AnalystOutput
    from app.features import FeatureSnapshot

    fake_features = FeatureSnapshot(
        snapshot_at=datetime.utcnow(),
        xau_price=2345.50,
        xau_price_fetched_at=datetime.utcnow(),
    )
    analyst_prompt = build_analyst_prompt(fake_features)
    console.print(Panel(
        analyst_prompt[:500] + "...",
        title="分析师提示词（前 500 字符）"
    ))

    fake_analyst = AnalystOutput(
        generated_at=datetime.utcnow(),
        direction="neutral",
        confidence=0.5,
        primary_drivers=["测试"],
        counter_drivers=[],
        narrative="测试叙事。",
        key_events=[],
    )
    planner_prompt = build_planner_prompt(fake_features, fake_analyst, 0.0, "neutral", {})
    console.print(Panel(
        planner_prompt[:500] + "...",
        title="规划师提示词（前 500 字符）"
    ))


@app.command()
def replay(snapshot_id: int = typer.Argument(..., help="要重放的快照 ID")):
    """使用历史快照的特征重放完整分析。"""
    setup_logging()
    session = _get_session()
    repo = SnapshotRepo(session)
    snap = repo.get_by_id(snapshot_id)

    if not snap:
        console.print(f"[red]快照 {snapshot_id} 不存在[/red]")
        session.close()
        return

    from app.features import FeatureSnapshot
    features = FeatureSnapshot(**snap.raw_features_json)
    horizon = snap.horizon_hours

    console.print(f"[cyan]正在重放快照 {snapshot_id}...[/cyan]")
    console.print(f"  原始价格: ${snap.xau_price:.2f}")
    console.print(f"  预测窗口: {horizon} 小时")

    new_snap = repo.create(
        horizon_hours=horizon,
        xau_price=features.xau_price,
        xau_price_fetched_at=features.xau_price_fetched_at,
        raw_features=features.model_dump(mode="json"),
        prompt_version=snap.prompt_version,
        model_version=snap.model_version,
        strategy_version=snap.strategy_version,
    )
    console.print(f"  新快照已创建: ID={new_snap.id}")

    from app.llm import build_provider, Analyst, Planner
    provider = build_provider()
    analyst = Analyst(provider)
    analyst_out = asyncio.run(analyst.analyze(features))
    repo.update_analyst_output(new_snap.id, analyst_out.to_dict())

    planner = Planner(provider)
    plan = asyncio.run(planner.plan(features, analyst_out, new_snap.id, horizon))
    repo.update_trade_plan(new_snap.id, plan.to_dict())

    session.close()
    console.print(f"[green]✓ 重放完成，新快照 ID={new_snap.id}[/green]")


if __name__ == "__main__":
    app()
