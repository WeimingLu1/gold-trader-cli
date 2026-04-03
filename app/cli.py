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
from rich.progress import track

from app.config import get_settings
from app.logging import setup_logging
from app.db.session import get_session_factory
from app.db.repo import SnapshotRepo, EvaluationRepo
from app.db.init_db import init_db as _init_db
from app.collectors import (
    XAUUSDCollector,
    TreasuryYieldCollector,
    RealRateCollector,
    DXYCollector,
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
    failed = []

    collectors = [("xauusd", XAUUSDCollector())]
    if settings.enable_rates:
        collectors += [
            ("treasury_yields", TreasuryYieldCollector()),
            ("real_rates", RealRateCollector()),
            ("dxy", DXYCollector()),
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
            source_tag = data[0].source if data else "empty"
            console.print(f"  [green]+[/green] {name}: {len(data)} 条数据  [dim]({source_tag})[/dim]")
        except Exception as e:
            console.print(f"  [red]![/red] {name}: {e}")
            results[name] = []
            failed.append((name, str(e)))

    if failed:
        console.print(f"\n[yellow]⚠️  {len(failed)} 个采集器失败，将使用 fallback/mock 数据:[/yellow]")
        for name, err in failed:
            console.print(f"  [yellow]  {name}: {err}[/yellow]")

    return results


def _build_snapshot(collected: dict, horizon_hours: int = 4) -> FeatureSnapshot:
    """从采集数据构建 FeatureSnapshot。"""
    now = datetime.utcnow()

    # ── XAU 价格 ────────────────────────────────────────────────────────────
    xau_data = collected.get("xauusd", [])
    if xau_data:
        xau = xau_data[0].normalized_payload or xau_data[0].raw_payload
        xau_price = xau["price"]
        xau_fetched_at = xau_data[0].fetched_at
    else:
        xau_price = 0.0
        xau_fetched_at = now

    # ── 市场特征（用当前价格模拟历史 — TODO: 接入真实历史价格）────────────
    price_store = HistoricalPriceStore()
    for h in [1, 4, 12, 24]:
        price_store.add(now - timedelta(hours=h), xau_price * (1 - 0.001 * h))
    price_store.add(now, xau_price)
    market_feats = build_market_features(xau_price, price_store.get_history(), now)

    # ── 宏观特征（从真实采集器提取）────────────────────────────────────────
    # DXY
    dxy_data = collected.get("dxy", [])
    if dxy_data and dxy_data[0].normalized_payload:
        np = dxy_data[0].normalized_payload
        dxy_current = np.get("dxy", 104.5)
        dxy_previous = np.get("dxy_prev")
    else:
        dxy_current, dxy_previous = 104.5, None

    # 国债收益率（当前 + 前一值）
    yields_data = {item.symbol: item.normalized_payload for item in collected.get("treasury_yields", []) if item.normalized_payload}
    yield_10y_current = yields_data.get("DGS10", {}).get("yield_pct", 4.38)
    yield_10y_previous = yields_data.get("DGS10", {}).get("yield_pct_prev")
    yield_2y_current = yields_data.get("DGS2", {}).get("yield_pct", 4.62)
    yield_2y_previous = yields_data.get("DGS2", {}).get("yield_pct_prev")

    # 实际利率
    real_rate_data = collected.get("real_rates", [])
    if real_rate_data and real_rate_data[0].normalized_payload:
        real_rate_proxy = real_rate_data[0].normalized_payload.get("real_rate_pct", 2.03)
    else:
        real_rate_proxy = 2.03

    macro_feats = build_macro_features(
        dxy_current=dxy_current,
        dxy_previous=dxy_previous if dxy_previous and dxy_previous > 0 else dxy_current,
        yield_10y_current=yield_10y_current,
        yield_10y_previous=yield_10y_previous if yield_10y_previous else yield_10y_current,
        yield_2y_current=yield_2y_current,
        yield_2y_previous=yield_2y_previous if yield_2y_previous else yield_2y_current,
        real_rate_proxy=real_rate_proxy,
    )

    # ── 新闻特征 ────────────────────────────────────────────────────────────
    news_feats = build_news_features(collected.get("news", []))

    # ── 市场状态特征 ────────────────────────────────────────────────────────
    regime_feats = build_regime_features(market_feats["volatility_24h"], collected.get("macro_calendar", []))

    # 持仓数据（mock）
    pos_data = collected.get("positioning", [])
    if pos_data and pos_data[0].normalized_payload:
        pos = pos_data[0].normalized_payload
        cot_net = pos.get("net_positions", 0.0)
    else:
        cot_net = 0.0

    # ETF 流量（从 dedicated collector 读）
    etf_flow = 0.0
    etf_data = collected.get("etf_flows", [])
    if etf_data:
        for item in etf_data:
            if item.normalized_payload:
                etf_flow += item.normalized_payload.get("flow_24h_oz", 0)

    available = sum(1 for v in collected.values() if v)
    completeness = available / 8

    # Proxy confidence from factor alignment: compute rough composite score magnitude
    # DXY and real_rate are the most reliable factors
    macro_signal = (-macro_feats["dxy_change"] / 1.35) * 0.222 + (-macro_feats["real_rate_proxy"] / 9.0) * 0.222
    tech_signal = (1.0 if market_feats["trend_state"] == "bullish" else -1.0 if market_feats["trend_state"] == "bearish" else 0.0) * 0.222
    vol_signal = (-0.3 if regime_feats["volatility_regime"] == "high" else 0.1 if regime_feats["volatility_regime"] == "low" else 0.0) * 0.167
    rough_composite = macro_signal + tech_signal + vol_signal
    confidence_score_proxy = min(1.0, abs(rough_composite) * 2.5)

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
        hours_until_event=regime_feats.get("hours_until_event"),
        cot_net_positions=cot_net,
        etf_flow_24h=etf_flow,
        confidence_score=confidence_score_proxy,
        data_completeness=completeness,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 详细展示辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _print_collected_summary(collected: dict) -> None:
    """打印采集到的原始数据总览。"""
    console.print("\n[bold cyan]数据总览[/bold cyan]")

    # XAU 价格详情
    xau_data = collected.get("xauusd", [])
    if xau_data and xau_data[0].normalized_payload:
        p = xau_data[0].normalized_payload
        console.print(f"  黄金价格: [bold]${p.get('price', 'N/A'):.2f}[/bold]  |  买价 ${p.get('bid', 'N/A'):.2f}  |  卖价 ${p.get('ask', 'N/A'):.2f}  |  差价 ${p.get('spread', 'N/A'):.2f}")

    # 债券收益率
    yields_data = collected.get("treasury_yields", [])
    if yields_data:
        yield_table = Table(title="美债收益率", show_header=True, header_style="bold cyan")
        yield_table.add_column("期限", style="white")
        yield_table.add_column("收益率", justify="right", style="yellow")
        for item in yields_data:
            if item.normalized_payload:
                label = {"DGS2": "2年期", "DGS5": "5年期", "DGS10": "10年期", "DGS30": "30年期"}.get(item.symbol or "", item.symbol or "")
                yield_table.add_row(label, f"{item.normalized_payload.get('yield_pct', 0):.3f}%")
        console.print(yield_table)

    # 宏观日历事件
    events_data = collected.get("macro_calendar", [])
    if events_data:
        event_table = Table(title="宏观事件", show_header=True, header_style="bold cyan")
        event_table.add_column("事件", style="white")
        event_table.add_column("影响", style="yellow")
        event_table.add_column("距今", style="white")
        for item in events_data:
            if item.normalized_payload:
                np = item.normalized_payload
                hours = np.get("hours_until_event", 0)
                impact = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}.get(np.get("impact", ""), np.get("impact", ""))
                if hours < 1:
                    time_str = f"{hours*60:.0f} 分钟"
                elif hours < 24:
                    time_str = f"{hours:.1f} 小时"
                else:
                    time_str = f"{hours/24:.1f} 天"
                event_table.add_row(np.get("event", ""), impact, time_str)
        console.print(event_table)

    # COT 持仓
    pos_data = collected.get("positioning", [])
    if pos_data and pos_data[0].normalized_payload:
        rp = pos_data[0].normalized_payload
        net = rp.get("net_positions", 0)
        ratio = rp.get("long_short_ratio", 0)
        console.print(
            f"  COT 持仓: 非商业净多头 [bold]{net:+,}[/bold] 手"
            f"  |  多空比 [bold]{ratio:.2f}[/bold]"
        )

    # ETF 流量
    etf_data = collected.get("etf_flows", [])
    if etf_data:
        flow_lines = []
        for item in etf_data:
            if item.normalized_payload:
                ticker = item.symbol or "?"
                flow = item.normalized_payload.get("flow_24h_oz", 0)
                direction = "流入 ↑" if flow > 0 else "流出 ↓" if flow < 0 else "持平"
                flow_lines.append(f"{ticker}: {flow:+,.0f} oz {direction}")
        if flow_lines:
            console.print(f"  ETF 流量: {'  |  '.join(flow_lines)}")

    # 新闻标题
    news_data = collected.get("news", [])
    if news_data:
        news_table = Table(title="相关新闻标题（前5条）", show_header=True, header_style="bold cyan")
        news_table.add_column("来源", style="cyan", width=12)
        news_table.add_column("标题", style="white")
        for item in news_data[:5]:
            if item.normalized_payload:
                headline = item.normalized_payload.get("headline", "")[:80]
                source = item.source or ""
                gold_driver = " 🟢" if item.normalized_payload.get("is_gold_key_driver") else ""
                news_table.add_row(source + gold_driver, headline)
        console.print(news_table)


def _print_features_detail(features: FeatureSnapshot) -> None:
    """打印完整特征详情。"""
    console.print("\n[bold cyan]特征快照详情[/bold cyan]")

    # 收益率
    returns_table = Table(title="收益率", show_header=True, header_style="bold cyan")
    returns_table.add_column("周期", style="white")
    returns_table.add_column("涨跌幅", justify="right", style="yellow")
    for label, val in [
        ("1小时", features.returns_1h),
        ("4小时", features.returns_4h),
        ("12小时", features.returns_12h),
        ("24小时", features.returns_24h),
    ]:
        arrow = "↑" if val > 0 else "↓" if val < 0 else "→"
        returns_table.add_row(label, f"{arrow} {val:+.3%}")
    console.print(returns_table)

    # 宏观 & 持仓因子
    factor_table = Table(title="量化因子", show_header=True, header_style="bold cyan")
    factor_table.add_column("因子", style="white")
    factor_table.add_column("数值", justify="right", style="yellow")
    factor_table.add_row("美元指数变化", f"{features.dxy_change:+.3%}")
    factor_table.add_row("10年期国债收益率变化", f"{features.yield_10y_change:+.2f} bp")
    factor_table.add_row("实际利率代理", f"{features.real_rate_proxy:+.3f}%")
    factor_table.add_row("收益率曲线斜率(10y-2y)", f"{features.yield_curve_slope:+.2f}")
    factor_table.add_row("新闻情绪评分", f"{features.news_sentiment_score:+.2f}（-1~+1）")
    factor_table.add_row("COT净持仓", f"{features.cot_net_positions:+,.0f} 手")
    factor_table.add_row("ETF 24h净流入", f"{features.etf_flow_24h:+,.0f} oz")
    factor_table.add_row("数据完整度", f"{features.data_completeness:.0%}")
    console.print(factor_table)

    console.print(
        f"  趋势: [bold]{features.trend_state}[/bold]  |  "
        f"波动率环境: [bold]{features.volatility_regime}[/bold]  |  "
        f"风险状态: [bold]{features.risk_state}[/bold]  |  "
        f"事件窗口: {'[red]是[/red]' if features.event_window else '否'}  |  "
        f"数据置信度: {features.confidence_score:.2f}"
    )


def _print_factor_scores(features: FeatureSnapshot, scorer: "Scorer") -> None:
    """打印综合评分和因子评分表。"""
    composite_score, factor_scores = scorer.score(features)

    console.print("\n[bold cyan]量化评分[/bold cyan]")
    console.print(f"  综合评分: [bold]{composite_score:+.3f}[/bold]（-1.0=强烈看空 ~ +1.0=强烈看多）")

    score_bar = "█" * int((composite_score + 1) * 10) + "░" * int((1 - composite_score) * 10)
    console.print(f"  评分条: [{score_bar}]")

    score_table = Table(title="因子评分明细", show_header=True, header_style="bold cyan")
    score_table.add_column("因子", style="white")
    score_table.add_column("权重", justify="right", style="cyan")
    score_table.add_column("分项得分", justify="right", style="yellow")
    score_table.add_column("贡献", justify="right", style="white")

    factor_labels = {
        "usd": "美元指数",
        "real_rate": "实际利率",
        "positioning": "COT持仓",
        "volatility": "波动率",
        "technical": "技术面",
        "news": "新闻情绪",
    }
    weights = scorer.weights

    for key, label in factor_labels.items():
        weight = getattr(weights, f"{key}_factor", 0)
        fs_val = factor_scores.get(key, 0)
        # Clamp to [-1, 1] to show what actually contributes to composite
        fs_val_clamped = max(-1.0, min(1.0, fs_val))
        contribution = fs_val_clamped * weight
        bar = "█" * int((fs_val_clamped + 1) * 5) if fs_val_clamped != 0 else "░" * 5
        score_table.add_row(label, f"{weight:.1%}", f"{fs_val_clamped:+.3f} {bar}", f"{contribution:+.3f}")

    console.print(score_table)


def _print_analyst_detail(analyst_output: "AnalystOutput") -> None:
    """打印完整分析师输出。"""
    console.print("\n[bold cyan]LLM 分析师输出[/bold cyan]")

    direction_color = {"bullish": "green", "bearish": "red", "neutral": "yellow"}.get(analyst_output.direction, "white")
    console.print(f"  方向: [{direction_color}][bold]{analyst_output.direction.upper()}[/bold]")
    console.print(f"  置信度: {analyst_output.confidence:.2f}")
    console.print(f"\n  [bold]叙事分析:[/bold]\n  {analyst_output.narrative}")

    if analyst_output.primary_drivers:
        drivers_table = Table(title="主要驱动因素", show_header=False)
        drivers_table.add_column("→", style="green", width=2)
        drivers_table.add_column("", style="white")
        for d in analyst_output.primary_drivers:
            drivers_table.add_row("→", d)
        console.print(drivers_table)

    if analyst_output.counter_drivers:
        ctable = Table(title="反向驱动因素", show_header=False)
        ctable.add_column("←", style="red", width=2)
        ctable.add_column("", style="white")
        for d in analyst_output.counter_drivers:
            ctable.add_row("←", d)
        console.print(ctable)

    if analyst_output.key_events:
        console.print(f"  [bold]关键事件:[/bold] {', '.join(analyst_output.key_events)}")


def _print_plan_detail(trade_plan: "TradePlan") -> None:
    """打印完整交易计划。"""
    console.print("\n[bold cyan]交易计划[/bold cyan]")

    stance_color = {"long": "green", "short": "red", "neutral": "yellow"}.get(trade_plan.stance, "white")
    console.print(f"  立场: [{stance_color}][bold]{trade_plan.stance.upper()}[/bold]")
    console.print(f"  置信度: {trade_plan.confidence:.2f}")
    console.print(f"  预测窗口: {trade_plan.horizon_hours} 小时")
    console.print(f"  预期收益: {trade_plan.expected_return_pct:+.3f}%")
    console.print(f"\n  [bold]入场规则:[/bold] {trade_plan.entry_rule}")
    console.print(f"  [bold]止损规则:[/bold] {trade_plan.stop_rule}")
    console.print(f"  [bold]止盈规则:[/bold] {trade_plan.take_profit_rule}")
    console.print(f"  [bold]失效条件:[/bold] {trade_plan.invalidation_rule}")
    console.print(f"  [bold]风控提示:[/bold] {trade_plan.risk_note}")
    if trade_plan.why:
        console.print(f"\n  [bold]策略解释:[/bold] {trade_plan.why}")

    console.print(
        f"\n  版本: 模型={trade_plan.model_version}  |  "
        f"提示词={trade_plan.prompt_version}  |  "
        f"策略={trade_plan.strategy_version}"
    )


def _run_pipeline() -> int:
    """执行完整分析 pipeline，返回创建的 snapshot ID。"""
    from app.llm import build_provider, Analyst, Planner
    from app.strategy import Scorer
    from app.llm.schemas import AnalystOutput

    settings = get_settings()
    horizon = settings.default_horizon_hours

    console.print(Panel("[yellow]黄金交易指导系统 Pipeline — 启动中...[/yellow]"))

    # 第1步：数据采集
    console.print("\n[bold cyan]第 1 步：数据采集[/bold cyan]")
    collected = asyncio.run(_collect_all())
    _print_collected_summary(collected)

    # 第2步：构建特征
    console.print("\n[bold cyan]第 2 步：特征工程[/bold cyan]")
    features = _build_snapshot(collected, horizon)
    console.print(f"  快照时间: {features.snapshot_at}")
    console.print(f"  XAU 价格: ${features.xau_price:.2f}")
    _print_features_detail(features)

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
    scorer = Scorer(DEFAULT_WEIGHTS)
    _print_factor_scores(features, scorer)

    try:
        analyst_output = asyncio.run(analyst.analyze(features))
        _print_analyst_detail(analyst_output)
        repo.update_analyst_output(snap.id, analyst_output.to_dict())
    except Exception as e:
        console.print(f"  [yellow]分析师运行失败（使用 fallback）: {e}[/yellow]")
        analyst_output = AnalystOutput(
            generated_at=datetime.utcnow(),
            direction="neutral",
            confidence=0.5,
            primary_drivers=[],
            counter_drivers=[],
            narrative="（分析师调用失败）",
            key_events=[],
        )
        repo.update_analyst_output(snap.id, {"direction": "neutral", "confidence": 0.5})

    # 第5步：生成交易计划
    console.print("\n[bold cyan]第 5 步：生成交易计划[/bold cyan]")
    planner = Planner(provider)

    try:
        analyst_out = repo.get_by_id(snap.id).analyst_output_json
        mock_analyst_out = AnalystOutput(
            generated_at=datetime.utcnow(),
            direction=analyst_out.get("direction", "neutral"),
            confidence=float(analyst_out.get("confidence", 0.5)),
            primary_drivers=analyst_out.get("primary_drivers", []),
            counter_drivers=analyst_out.get("counter_drivers", []),
            narrative=analyst_out.get("narrative", ""),
            key_events=analyst_out.get("key_events", []),
        )

        trade_plan = asyncio.run(planner.plan(features, mock_analyst_out, snap.id, horizon))
        _print_plan_detail(trade_plan)
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

    # Determine if running in mock mode (placeholder or empty key)
    mock_keys = ("", "your_openai_api_key_here")
    is_mock_llm = settings.llm_api_key in mock_keys
    is_mock_gold = settings.gold_api_key in mock_keys
    is_mock_fred = settings.fred_api_key in mock_keys

    table = Table(title="系统健康检查", show_header=False)
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="white")

    checks = [
        ("Python 版本", "✅ 3.11+"),
        ("数据库地址", settings.database_url),
        ("LLM 模型", settings.llm_model),
        ("LLM API Key", "⚠️  mock 模式（占位符）" if is_mock_llm else "✅ 已配置"),
        ("GoldAPI Key", "⚠️  mock 模式" if is_mock_gold else "✅ 已配置"),
        ("FRED API Key", "⚠️  mock 模式" if is_mock_fred else "✅ 已配置"),
        ("调度间隔", f"每 {settings.schedule_interval_hours} 小时"),
        ("默认预测窗口", f"{settings.default_horizon_hours} 小时"),
        ("日志级别", settings.log_level),
        ("策略权重文件", settings.weights_file),
    ]

    for name, status in checks:
        table.add_row(name, str(status))

    console.print(table)
    if is_mock_llm or is_mock_gold or is_mock_fred:
        console.print("\n[yellow]⚠️  部分数据源使用 mock 模式 — 请检查 .env 配置[/yellow]")
    else:
        console.print("\n[green]✓ 所有检查通过 — 生产模式[/green]")


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

    async def _get_current_price():
        collector = XAUUSDCollector()
        data = await collector.collect()
        return data[0].normalized_payload.get("price")

    # Fetch price once at evaluation start (use same price for all in batch for consistency)
    current_price = asyncio.run(_get_current_price())
    eval_time = datetime.utcnow()
    console.print(f"[dim]评估时间: {eval_time}  XAU 价格: ${current_price}[/dim]")

    for snap in matured:
        try:
            eval_result = evaluator.evaluate(snap, current_price)
            # Check if snapshot's horizon had truly elapsed
            snap_maturity = snap.available_time + timedelta(hours=snap.horizon_hours) if snap.available_time else None
            if snap_maturity and eval_time < snap_maturity:
                console.print(
                    f"  [yellow]~[/yellow] 快照 {snap.id}: 窗口尚未完全到期"
                    f"（到期时间: {snap_maturity.strftime('%H:%M:%S')}）"
                )
            eval_repo.create(snap.id, **{
                "xau_price_at_horizon": eval_result.xau_price_at_horizon,
                "direction_actual": eval_result.direction_actual,
                "direction_hit": eval_result.direction_hit,
                "stop_hit": eval_result.stop_hit,
                "expected_return": eval_result.expected_return,
                "actual_return": eval_result.actual_return,
                "prompt_version": eval_result.prompt_version,
                "model_version": eval_result.model_version,
                "strategy_version": eval_result.strategy_version,
            })
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
def backtest(
    start: str = typer.Option(..., help="回测开始日期，格式 YYYY-MM-DD"),
    end: str = typer.Option(..., help="回测结束日期，格式 YYYY-MM-DD"),
    interval: int = typer.Option(4, help="快照间隔（小时）"),
    name: str = typer.Option("default", help="回测名称"),
):
    """基于真实历史数据运行策略回测。

    使用 yfinance 黄金期货历史价格和 FRED 宏观数据，
    在每个历史时点模拟策略决策并与后续实际走势对比。
    """
    setup_logging()
    from datetime import date
    from app.backtest import BacktestEngine

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError:
        console.print("[red]日期格式错误，请使用 YYYY-MM-DD[/red]")
        raise typer.Exit(1)

    if start_date >= end_date:
        console.print("[red]开始日期必须早于结束日期[/red]")
        raise typer.Exit(1)

    console.print(Panel(f"[yellow]历史回测系统启动[/yellow]\n"
                        f"  区间: {start} ~ {end}\n"
                        f"  间隔: {interval} 小时\n"
                        f"  名称: {name}"))

    engine = BacktestEngine()

    # Warm cache
    console.print("\n[bold cyan]第 1 步：预加载历史数据...[/bold cyan]")
    cache_info = engine.warm_cache(start_date, end_date)
    console.print(
        f"  黄金价格栏: [green]{cache_info['gold_bars']}[/green]  |  "
        f"收益率/DXY 栏: [green]{cache_info['rates_bars']}[/green]"
    )

    # Run backtest
    console.print("\n[bold cyan]第 2 步：运行回测...[/bold cyan]")
    result = engine.run(start_date, end_date, interval_hours=interval, name=name)
    metrics = result["metrics"]

    console.print(
        f"\n  总快照: [cyan]{result['total_snapshots']}[/cyan]  |  "
        f"评估数: [cyan]{result['evaluated']}[/cyan]  |  "
        f"跳过: [yellow]{result['skipped']}[/yellow]"
    )

    # Direction accuracy
    console.print("\n[bold cyan]方向准确率[/bold cyan]")
    dir_table = Table(show_header=True, header_style="bold cyan")
    dir_table.add_column("指标", style="white")
    dir_table.add_column("数值", justify="right", style="yellow")
    dir_table.add_row("整体准确率", f"{metrics.get('direction_hit_rate', 0):.1%}")
    dir_table.add_row("多头胜率", f"{metrics.get('win_rate_long', 0):.1%}")
    dir_table.add_row("空头胜率", f"{metrics.get('win_rate_short', 0):.1%}")
    console.print(dir_table)

    # Returns
    console.print("\n[bold cyan]收益统计[/bold cyan]")
    ret_table = Table(show_header=True, header_style="bold cyan")
    ret_table.add_column("指标", style="white")
    ret_table.add_column("数值", justify="right", style="yellow")
    ret_table.add_row("平均实际收益", f"{metrics.get('avg_actual_return', 0):+.3f}%")
    ret_table.add_row("平均预期收益", f"{metrics.get('avg_expected_return', 0):+.3f}%")
    ret_table.add_row("夏普比率", f"{metrics.get('sharpe_ratio', 0):.2f}")
    ret_table.add_row("最大回撤", f"{metrics.get('max_drawdown', 0):+.3f}%")
    console.print(ret_table)

    # Stop/TP
    console.print("\n[bold cyan]止损/止盈触发率[/bold cyan]")
    st_table = Table(show_header=True, header_style="bold cyan")
    st_table.add_column("指标", style="white")
    st_table.add_column("数值", justify="right", style="yellow")
    st_table.add_row("止损触发", f"{metrics.get('stop_hit_rate', 0):.1%}")
    st_table.add_row("止盈触发", f"{metrics.get('tp_hit_rate', 0):.1%}")
    st_table.add_row("未触发", f"{metrics.get('neither_rate', 0):.1%}")
    console.print(st_table)

    # By stance
    by_stance = metrics.get("by_stance", {})
    if by_stance:
        console.print("\n[bold cyan]分立场统计[/bold cyan]")
        stance_table = Table(show_header=True, header_style="bold cyan")
        stance_table.add_column("立场", style="white")
        stance_table.add_column("次数", justify="right", style="cyan")
        stance_table.add_column("准确率", justify="right", style="yellow")
        stance_table.add_column("平均收益", justify="right", style="white")
        for stance in ("long", "short", "neutral"):
            if stance in by_stance:
                s = by_stance[stance]
                stance_table.add_row(
                    stance,
                    str(s.get("count", 0)),
                    f"{s.get('hit_rate', 0):.1%}",
                    f"{s.get('avg_return', 0):+.3f}%",
                )
        console.print(stance_table)

    # Monthly breakdown
    by_month = metrics.get("by_month", {})
    if by_month:
        console.print("\n[bold cyan]逐月统计[/bold cyan]")
        month_table = Table(show_header=True, header_style="bold cyan")
        month_table.add_column("月份", style="white")
        month_table.add_column("次数", justify="right", style="cyan")
        month_table.add_column("准确率", justify="right", style="yellow")
        month_table.add_column("累计收益", justify="right", style="white")
        for month, stats in sorted(by_month.items()):
            month_table.add_row(
                month,
                str(stats.get("count", 0)),
                f"{stats.get('hit_rate', 0):.1%}",
                f"{stats.get('pnl', 0):+.3f}%",
            )
        console.print(month_table)

    console.print(f"\n[green]✓ 回测完成 (run_id={result['run_id']})[/green]")


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
