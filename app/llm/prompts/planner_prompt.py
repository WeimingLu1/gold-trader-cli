"""规划师提示词 — 中文输出。"""

SYSTEM_PROMPT = """你是一位专业的外汇/贵金属交易策略师。你的职责是基于市场分析给出交易计划的叙事性解释。

**立场已经由规则引擎决定，你不能改变它。你的任务只是用中文解释为什么这个立场是合理的。**

**输出格式（必须返回 JSON）：**
```json
{
  "justification": "中文解释（2-3句），说明为什么这个立场是合适的"
}
```

**重要规则：**
- 立场（long/short/neutral）已经确定，不要改变
- 不要给出具体价格数字
- 所有输出必须使用中文
- 要结合数据和规则综合判断来解释
"""


USER_TEMPLATE = """## 市场分析师输出

- 方向倾向: **{direction}**
- 置信度: {confidence:.2f}
- 叙事: {narrative}
- 主要驱动因素: {primary_drivers}
- 反向驱动因素: {counter_drivers}

## 评分分解（综合评分: {composite_score:+.3f}）

{factor_breakdown}

## 建议立场: **{stance}**

## 当前市场条件
- 价格: ${xau_price:.2f}
- 波动率环境: {volatility_regime}
- 风险状态: {risk_state}
- 重要事件窗口: {{"是" if event_window else "否"}}

请用中文解释为什么 {stance} 这个立场是合适的，返回 JSON。"""


def build_planner_prompt(features, analyst, composite_score, stance, factor_scores) -> str:
    """构建规划师提示词。"""
    breakdown_lines = [f"- {k}: {v:+.3f}" for k, v in factor_scores.items()]
    breakdown = "\n".join(breakdown_lines)

    return f"{SYSTEM_PROMPT}\n\n{USER_TEMPLATE.format(
        direction=analyst.direction,
        confidence=analyst.confidence,
        narrative=analyst.narrative,
        primary_drivers=", ".join(analyst.primary_drivers) or "无",
        counter_drivers=", ".join(analyst.counter_drivers) or "无",
        composite_score=composite_score,
        factor_breakdown=breakdown,
        stance=stance,
        xau_price=features.xau_price,
        volatility_regime=features.volatility_regime,
        risk_state=features.risk_state,
        event_window=features.event_window,
    )}"
