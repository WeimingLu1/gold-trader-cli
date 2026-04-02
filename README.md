# Gold Trader CLI — 黄金交易指导系统

> 这是一个**交易指导系统**，不是自动下单机器人。它产生结构化、可解释的交易建议，并附带完整的事后表现评估。

---

## 功能概览

系统按配置间隔（默认每 4 小时）运行：

1. **采集** 市场、宏观、新闻数据（真实 API）
2. **构建** 结构化特征快照
3. **分析** 市场状态（LLM 驱动）
4. **生成** 规则约束下的交易计划
5. **记录** 每条建议到 SQLite 数据库
6. **评估** 预测窗口到期后的实际表现
7. **报告** 准确率、收益率、止损/止盈触发率等指标

---

## 快速开始

```bash
# 进入项目目录
cd gold-trader-cli

# 激活虚拟环境
source .venv/bin/activate

# 初始化数据库（首次使用）
gold-cli init-db

# 检查系统配置和 API 连通状态
gold-cli doctor

# 运行一次完整分析（即时查看当前市场建议）
gold-cli run-once

# 启动定时调度器（每 4 小时自动运行一次）
gold-cli schedule-start
```

---

## 配置文件说明（.env）

从 `.env.example` 复制并填写以下关键变量：

```bash
cp .env.example .env
```

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./gold_trader.db` | SQLite 数据库路径 |
| `LLM_MODEL` | `MiniMax-M2.7` | LLM 模型名称 |
| `LLM_API_KEY` | _(必填)_ | LLM API 密钥 |
| `LLM_BASE_URL` | MiniMax 平台地址 | API 基础地址 |
| `GOLD_API_KEY` | _(必填)_ | GoldAPI.io key |
| `FRED_API_KEY` | _(必填)_ | FRED API key（免费） |
| `NEWS_API_KEY` | _(必填)_ | NewsAPI.org key |
| `SCHEDULE_INTERVAL_HOURS` | `4` | 调度间隔（小时） |
| `DEFAULT_HORIZON_HOURS` | `4` | 默认预测窗口（小时） |

---

## 完整运行流程

```
定时触发（schedule-start）或手动触发（run-once）
       │
   第1步: 数据采集
   ├─ GoldAPI    → XAUUSD 实时价格（买价/卖价/点差）
   ├─ FRED       → 美债收益率（2y/5y/10y/30y）+ TIPS 实际利率
   ├─ NewsAPI    → 相关财经新闻标题
   └─ 宏观日历   → FOMC、CPI 等重要事件及距开启时间
       │
   第2步: 特征工程
   ├─ 计算 1h/4h/12h/24h 收益率
   ├─ 量化 6 个因子：美元指数、实际利率、COT持仓、波动率、技术面、新闻情绪
   ├─ 综合评分（-1.0 强烈看空 ~ +1.0 强烈看多）
   └─ 判断：波动率环境（低/正常/高）、趋势状态、风险状态、事件窗口
       │
   第3步: 保存快照到 SQLite
   （记录带 available_time，防止 look-ahead bias）
       │
   第4步: LLM 市场分析师（MiniMax M2.7）
   输入：结构化特征
   输出：方向（bullish/bearish/neutral）
        置信度（0.0~1.0）
        主要驱动因素 + 反向驱动因素
        完整叙事分析
        关键事件
       │
   第5步: 规则引擎 + LLM 规划器
   ├─ 规则引擎：综合评分 → 立场（long / short / neutral）
   │   · ±0.25 阈值，低置信度强制中立
   │   · 高波动/事件窗口/数据不完整 → 强制中立
   ├─ 风险引擎：计算止损/止盈价格（ATR 模式化）
   └─ LLM 规划器：用中文解释"为什么这个立场是合理的"
       │
   数据写入数据库，完成
       │
   ─── 预测窗口到期后（如4小时后）───────────────────
       │
   evaluate-pending：拉取真实价格，对比预测与实际
   ├─ 方向准确率（预测与实际方向是否一致）
   ├─ 止损触发率
   ├─ 止盈触发率
   └─ 实际收益率
       │
   report-daily：按日统计
   report-weekly：按周统计（支持按因子/置信度分组）
```

---

## 场景化使用指南

### 场景一：立即查看当前市场分析

```bash
gold-cli run-once
```

一次完整运行：采集 → 特征 → LLM分析 → 生成计划 → 打印详细输出（约30秒）。

**输出包含：**
- XAU 价格详情（买价/卖价/点差）
- 美债收益率（2y/5y/10y/30y）
- 宏观事件（FOMC/CPI）及距开启时间
- 前5条相关新闻标题
- 各周期收益率（1h/4h/12h/24h）
- 6个因子量化评分（含权重和贡献）
- 综合评分可视化条
- LLM 完整叙事分析
- 主要/反向驱动因素、关键事件
- 入场/止损/止盈/失效规则
- 策略解释和预期收益

---

### 场景二：启动自动定时交易指导

```bash
gold-cli schedule-start
```

每4小时（可配置）自动跑一次，所有结果存入数据库。适合开机后持续运行。

---

### 场景三：查看历史预测表现

```bash
# 评估所有预测窗口已到期的快照
gold-cli evaluate-pending

# 查看日报（默认今天）
gold-cli report-daily

# 查看指定日期日报
gold-cli report-daily 2026-04-01

# 查看周报（默认本周）
gold-cli report-weekly

# 查看指定周周报
gold-cli report-weekly 2026-03-23
```

> 注意：只有预测窗口已到期的快照才能被评估。如刚跑了一条4小时预测，需等4小时后才有数据可评估。

---

### 场景四：单独调试某个步骤

```bash
gold-cli collect        # 只采集数据，打印原始返回
gold-cli snapshot       # 采集 + 构建特征快照
gold-cli analyze        # 对当前数据运行 LLM 分析师
gold-cli plan-generate  # 生成交易计划
gold-cli plan-generate --snapshot-id 10  # 指定历史快照生成计划
```

---

### 场景五：用历史数据重放分析

```bash
# 用 ID=10 的快照特征重新跑一遍分析
gold-cli replay 10
```

用于对比不同提示词或策略版本的表现差异。

---

### 场景六：查看和调整策略权重

```bash
# 查看当前 6 因子的权重配置
gold-cli weights-show

# 修改 config/weights.yaml 后，下次 run-once 自动生效
```

---

### 场景七：查看系统状态

```bash
gold-cli doctor          # 检查 API 连通性和配置
gold-cli config-show    # 显示当前完整配置
gold-cli prompts-list   # 预览当前提示词内容
```

---

### 场景八：手动管理数据库

```bash
# 查看所有快照
sqlite3 gold_trader.db "SELECT id, status, stance, confidence, created_at FROM snapshots ORDER BY id DESC;"

# 查看评估结果
sqlite3 gold_trader.db "SELECT * FROM evaluations;"

# 删除测试数据（慎用）
sqlite3 gold_trader.db "DELETE FROM snapshots WHERE id > 1;"
```

---

## CLI 命令一览

| 命令 | 说明 |
|---|---|
| `init-db` | 初始化数据库表 |
| `doctor` | 检查系统配置和 API 连通状态 |
| `config-show` | 显示当前完整配置 |
| `collect` | 仅运行数据采集 |
| `snapshot` | 采集数据并创建特征快照 |
| `analyze` | 对当前数据运行 LLM 分析师 |
| `plan-generate` | 生成交易指导计划 |
| `run-once` | **核心命令**：运行完整 pipeline 一次 |
| `schedule-start` | 启动定时调度器 |
| `evaluate-pending` | 评估所有窗口已到期的预测 |
| `report-daily [日期]` | 生成日报 |
| `report-weekly [周起始]` | 生成周报 |
| `weights-show` | 显示当前策略权重 |
| `prompts-list` | 预览当前提示词 |
| `replay <id>` | 用历史快照重放分析 |

---

## 已接入的真实数据

| 数据 | API | 来源 |
|---|---|---|
| 黄金价格（XAUUSD） | GoldAPI.io | 实时报价 |
| 美债收益率（2y/5y/10y/30y） | FRED | 美国财政部 |
| 实际利率（TIPS） | FRED | TIPS 市场 |
| 新闻事件 | NewsAPI.org | 全球财经新闻 |
| LLM 分析 | MiniMax M2.7 | MiniMax 平台 |

> COT 持仓数据采集器已实现（CFTC，周更新），待接入。

---

## 架构设计

```
collectors/     → 数据采集层（XAUUSD、债券收益率、新闻、宏观日历）
features/       → 特征工程（市场特征、宏观特征、新闻特征、状态特征）
llm/            → LLM 层（Provider 抽象 + Analyst + Planner）
strategy/       → 策略层（评分引擎、规则引擎、风险管理、权重配置）
evaluation/     → 评估层（事后评估、指标计算、报表生成）
db/             → 数据库（SQLAlchemy ORM）
scheduler/      → 调度层（APScheduler）
cli/            → 命令行界面（Typer）
```

**核心设计原则：**
- 所有 LLM 输出使用结构化 JSON Schema
- **规则先于 LLM 做决策** — 模型负责研究归纳，规则负责交易决策
- 每次建议都记录版本（模型版本、提示词版本、策略版本）
- 所有数据标注 `available_time`，防止 look-ahead bias
- 采集层全部可 mock，方便开发和回测

---

## 数据库结构

默认使用 SQLite。包含以下表：

- **snapshots** — 每次预测快照（特征、分析输出、交易计划）
- **evaluations** — 事后评估结果（方向准确、止损/止盈触发、收益）
- **model_versions** — LLM 模型版本记录
- **prompt_versions** — 提示词版本记录
- **strategy_versions** — 策略权重配置版本

---

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## 项目结构

```
gold-trader-cli/
├─ app/
│  ├─ cli.py                 # Typer CLI 入口
│  ├─ config.py             # Pydantic Settings
│  ├─ scheduler.py           # APScheduler 调度器
│  ├─ logging.py             # Loguru 日志配置
│  ├─ db/
│  │   ├─ models.py          # 5 张数据库表
│  │   ├─ repo.py            # CRUD 操作
│  │   ├─ session.py         # 数据库会话
│  │   └─ init_db.py         # init-db 命令
│  ├─ collectors/
│  │   ├─ base.py            # BaseCollector 抽象
│  │   ├─ market_data.py     # XAUUSD 价格（GoldAPI.io）
│  │   ├─ rates.py           # 债券收益率（FRED）
│  │   ├─ news.py            # 新闻（NewsAPI.org）
│  │   ├─ macro_calendar.py   # 宏观日历
│  │   ├─ positioning.py      # COT 持仓
│  │   └─ etf_flows.py        # ETF 流量
│  ├─ features/
│  │   ├─ base.py            # FeatureSnapshot Pydantic 模型
│  │   ├─ market_features.py
│  │   ├─ macro_features.py
│  │   ├─ news_features.py
│  │   └─ regime_features.py
│  ├─ llm/
│  │   ├─ provider.py        # Provider 抽象（Mock + OpenAI）
│  │   ├─ schemas.py         # Pydantic 输出 Schema
│  │   ├─ analyst.py         # 市场分析师
│  │   ├─ planner.py         # 交易计划生成器
│  │   └─ prompts/           # 提示词模板
│  ├─ strategy/
│  │   ├─ scorer.py         # 多因子评分引擎
│  │   ├─ rules.py          # 规则引擎
│  │   ├─ risk.py            # 风险管理
│  │   └─ weights.py         # 权重配置
│  ├─ evaluation/
│  │   ├─ evaluator.py       # 评估逻辑
│  │   ├─ metrics.py         # 指标计算
│  │   └─ reports.py         # 报表生成
│  └─ utils/
│      └─ time_utils.py      # 时间工具
├─ tests/                    # 测试套件
├─ config/
│  └─ weights.yaml          # 默认策略权重
├─ logs/                     # 日志文件（运行时创建）
├─ pyproject.toml
├─ .env.example
└─ README.md
```

---

## 未来扩展方向

- [ ] COT 持仓数据接入（CFTC，周更新）
- [ ] 回测引擎（基于历史数据）
- [ ] 多时间周期分析（15m、1h、4h、日线）
- [ ] 多品种支持（白银、矿业股、外汇）
- [ ] 告警通知（Slack、邮件）
- [ ] Web 控制台
- [ ] 多 Agent 架构（宏观分析师、技术分析师、情绪分析师）
- [ ] 策略 A/B 测试与集成学习
