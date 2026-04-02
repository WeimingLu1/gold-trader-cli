"""分析师提示词 — 中文输出。"""

SYSTEM_PROMPT = """你是一位专业的黄金（XAUUSD）市场分析师。你的职责是：

1. 研究提供的市场数据，识别关键价格模式
2. 判断黄金短期方向：看多（bullish）、看空（bearish）、还是中立（neutral）
3. 给出置信度（0.0 到 1.0）
4. 列出主要驱动因素和反向因素
5. 用中文写一段简洁的叙事分析（2-4 句）

**输出格式（必须返回 JSON）：**
```json
{
  "direction": "bullish" | "bearish" | "neutral",
  "confidence": 0.0 到 1.0 的浮点数,
  "primary_drivers": ["驱动因素1", "驱动因素2"],
  "counter_drivers": ["反向因素1"],
  "narrative": "中文叙事分析（2-4句）",
  "key_events": ["重要事件1", "重要事件2"]
}
```

**重要规则：**
- 不要给出具体入场/出场价格，那是交易计划模块的职责
- 不要做交易决策，只做研究和分析
- 叙事和所有输出必须使用中文
- 置信度要结合数据完整性和信号强度综合判断
"""


USER_TEMPLATE = """## XAUUSD 市场快照

**时间:** {snapshot_time}
**价格:** ${xau_price:.2f}

### 收益率与趋势
- 1小时: {returns_1h:+.3%}
- 4小时: {returns_4h:+.3%}
- 12小时: {returns_12h:+.3%}
- 24小时: {returns_24h:+.3%}
- 趋势状态: **{trend_state}**
- 波动率 4h: {volatility_4h:.2%}
- 波动率 24h: {volatility_24h:.2%}

### 宏观数据
- 美元指数变化: {dxy_change:+.3%}
- 10年期国债收益率变化: {yield_10y_change:+.2f} 个基点
- 实际利率代理: {real_rate_proxy:+.3%}
- 收益率曲线斜率: {yield_curve_slope:+.2f}

### 新闻与情绪
- 情绪评分: {news_sentiment_score:+.2f}（范围 -1 到 +1）
- 事件强度: {news_event_intensity:.2f}
- 是否为黄金关键驱动: {{"是" if is_gold_key_driver else "否"}}

### 市场状态
- 风险状态: **{risk_state}**
- 波动率环境: **{volatility_regime}**
- 重要事件窗口: {{"是" if event_window else "否"}}

### 持仓与资金流
- COT 净持仓: {cot_net_positions:,.0f} 手合约
- ETF 24小时净流入: {etf_flow_24h:,.0f} 盎司

### 数据质量
- 置信度评分: {confidence_score:.2f}
- 数据完整度: {data_completeness:.0%}

---

请分析以上数据，返回中文 JSON 输出。"""


def build_analyst_prompt(features) -> str:
    """构建分析师提示词。"""
    return f"{SYSTEM_PROMPT}\n\n{USER_TEMPLATE.format(
        snapshot_time=features.snapshot_at.strftime("%Y-%m-%d %H:%M UTC"),
        xau_price=features.xau_price,
        returns_1h=features.returns_1h,
        returns_4h=features.returns_4h,
        returns_12h=features.returns_12h,
        returns_24h=features.returns_24h,
        trend_state=features.trend_state,
        volatility_4h=features.volatility_4h,
        volatility_24h=features.volatility_24h,
        dxy_change=features.dxy_change,
        yield_10y_change=features.yield_10y_change,
        real_rate_proxy=features.real_rate_proxy,
        yield_curve_slope=features.yield_curve_slope,
        news_sentiment_score=features.news_sentiment_score,
        news_event_intensity=features.news_event_intensity,
        is_gold_key_driver=features.is_gold_key_driver,
        risk_state=features.risk_state,
        volatility_regime=features.volatility_regime,
        event_window=features.event_window,
        cot_net_positions=features.cot_net_positions,
        etf_flow_24h=features.etf_flow_24h,
        confidence_score=features.confidence_score,
        data_completeness=features.data_completeness,
    )}"
