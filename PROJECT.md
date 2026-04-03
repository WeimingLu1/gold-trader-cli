# gold-trader-cli 项目详解

> 作者：Mia 🧠 | 首次深入分析：2026-04-02

---

## 一、项目定位

**这不是自动交易机器人**，而是一个**交易指导系统**：
- 产生结构化、可解释的交易建议
- 附带完整的事后表现评估
- 主要输出给人工交易员参考

---

## 二、技术架构

### 核心流程（Pipeline）
```
数据采集 → 特征构建 → LLM分析 → 规则评分 → 交易计划 → 数据库记录 → 事后评估
```

### 目录结构
```
app/
├── collectors/       # 数据采集器
│   ├── market_data.py      # XAUUSD实时价格
│   ├── rates.py            # 美国国债收益率 + 实际利率
│   ├── news.py             # 新闻数据
│   ├── macro_calendar.py   # 宏观事件日历
│   ├── positioning.py      # COT持仓数据
│   └── etf_flows.py        # ETF资金流向
│
├── features/        # 特征工程
│   ├── market_features.py  # 市场技术特征
│   ├── macro_features.py    # 宏观特征
│   ├── news_features.py     # 新闻特征
│   ├── regime_features.py   # 市场状态/波动率 regime
│   └── base.py              # FeatureSnapshot 统一数据结构
│
├── llm/             # LLM驱动模块
│   ├── analyst.py   # 市场分析师（判断方向/信心）
│   ├── planner.py   # 交易计划生成器
│   ├── provider.py  # LLM provider封装
│   ├── schemas.py  # Pydantic数据结构
│   └── prompts/    # 提示词
│
├── strategy/       # 规则引擎
│   ├── scorer.py   # 多因子评分
│   ├── rules.py    # 规则→立场映射 + 风控规则
│   ├── risk.py     # 风险管理（止损/止盈计算）
│   └── weights.py  # 因子权重配置
│
├── evaluation/     # 事后评估
│   ├── evaluator.py # 比较预测 vs 实际价格
│   ├── metrics.py  # 评估指标
│   └── reports.py  # 日报/周报生成
│
├── db/             # 数据库层
│   ├── models.py   # SQLAlchemy ORM模型
│   ├── session.py  # DB会话管理
│   ├── repo.py     # Repository模式
│   └── init_db.py  # 初始化
│
├── scheduler.py    # APScheduler定时调度
└── cli.py          # Typer CLI入口（31k大文件）
```

---

## 三、数据模型

### Snapshot（快照）
每次运行创建的完整记录：
- `xau_price` — 入金价
- `raw_features_json` — 原始特征
- `analyst_output_json` — LLM分析输出
- `trade_plan_json` — 交易计划
- `status` — `pending → matured → evaluated`

### Evaluation（评估）
预测到期后对比实际价格：
- `direction_hit` — 方向判断是否正确
- `stop_hit` — 止损/止盈/无触发
- `expected_return` vs `actual_return`

---

## 四、LLM 分析流程

### Analyst（分析师）
输入：FeatureSnapshot
输出：
- `direction` — bullish/bearish/neutral
- `confidence` — 0.0~1.0
- `primary_drivers` — 主要驱动因素
- `counter_drivers` — 反向因素
- `narrative` — 叙事性解释

### Planner（计划员）
**关键原则：LLM提议，规则验证和约束**

1. **Scorer** 计算复合分数（各因子加权）
2. **RuleEngine** 把分数映射为立场（long/short/neutral）
3. **RiskManager** 计算止损/止盈距离
4. **LLM** 只负责生成"为什么这样做"的叙事

---

## 五、策略评分权重（config/weights.yaml）

| 因子 | 权重 |
|------|------|
| 美元因素 | 20% |
| 实际利率因素 | 20% |
| 持仓因素 | 15% |
| 波动率因素 | 15% |
| 技术因素 | 20% |
| 新闻因素 | 10% |

---

## 六、风控规则（RuleEngine）

1. **低信心（<0.3）** → 强制 neutral
2. **高波动环境** → 降低敞口或强制 neutral
3. **重要宏观事件窗口（4小时内）** → 强制 neutral
4. **数据完整度 < 50%** → 强制 neutral

---

## 七、评估指标

- 方向准确率（direction_hit）
- 止损/止盈触发率
- 预期收益 vs 实际收益
- 日报/周报自动生成

---

## 八、调度运行

- **默认间隔：** 每4小时
- **调度器：** APScheduler BlockingScheduler
- **命令：** `gold-cli schedule-start`

---

## 九、数据库

- **类型：** SQLite（`gold_trader.db`）
- **表：** snapshots, evaluations, model_versions, prompt_versions, strategy_versions

---

## 十、依赖技术栈

- Python 3.11+
- Typer（CLI）
- SQLAlchemy 2.0（Pydantic集成）
- Pydantic v2
- APScheduler（定时）
- httpx（HTTP客户端）
- Loguru（日志）
- Rich（终端美化输出）

---

## 十一、我的维护备忘录

### 常见任务
- `gold-cli doctor` — 检查API连通性
- `gold-cli run-once` — 手动触发一次完整pipeline
- `gold-cli evaluate-pending` — 评估到期的预测
- `gold-cli report-daily` — 生成日报
- `gold-cli schedule-start` — 启动定时调度

### 需要关注
1. `.env` 中的API keys配置
2. `config/weights.yaml` 权重调整
3. `logs/` 日志文件增长
4. 数据库 `gold_trader.db` 大小
5. `app/strategy/rules.py` 中的 `LONG_THRESHOLD` 和 `SHORT_THRESHOLD` 校准

### 潜在风险
- 新闻API频率限制
- LLM API成本
- 数据源中断导致特征不完整

### 已完成的扩展
- ✅ **历史回测系统** (`gold-cli backtest`)：用 yfinance 黄金期货 + FRED 数据回测规则策略
  - 数据源：`history/` 模块（SQLite 缓存）
  - 核心引擎：`backtest/engine.py`
  - 评估指标：`backtest/metrics.py`
  - 已知问题：策略阈值过于保守（见 CLAUDE.md 已知问题部分）
