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

## 已接入的真实数据

| 数据 | API | 来源 |
|---|---|---|
| 黄金价格（XAUUSD） | GoldAPI.io | 实时报价 |
| 美债收益率（2y/5y/10y/30y） | FRED | 美国财政部 |
| 实际利率（TIPS） | FRED | TIPS 市场 |
| 新闻事件 | NewsAPI.org | 全球财经新闻 |
| LLM 分析 | MiniMax M2.7 | MiniMax 平台 |

---

## 快速开始

```bash
# 进入项目目录
cd gold-trader-cli

# 激活虚拟环境（如已激活可跳过）
source .venv/bin/activate

# 初始化数据库（首次使用）
gold-cli init-db

# 检查系统配置和 API 连通状态
gold-cli doctor

# 运行一次完整分析
gold-cli run-once

# 启动定时调度（每 4 小时自动运行一次）
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

## CLI 命令一览

| 命令 | 说明 |
|---|---|
| `init-db` | 初始化数据库表 |
| `doctor` | 检查系统配置和 API 连通状态 |
| `config-show` | 显示当前完整配置 |
| `collect` | 仅运行数据采集 |
| `snapshot` | 创建特征快照（打印到控制台） |
| `analyze` | 对当前数据运行 LLM 分析师 |
| `plan-generate` | 生成交易指导计划 |
| `run-once` | **核心命令**：运行完整 pipeline 一次 |
| `schedule-start` | 启动定时调度器 |
| `evaluate-pending` | 评估已成熟的预测 |
| `report-daily` | 生成日报 |
| `report-weekly` | 生成周报 |
| `weights-show` | 显示当前策略权重 |
| `prompts-list` | 预览当前提示词 |
| `replay <id>` | 用历史快照重放分析 |

---

## 工作流程

```
第 1 步：数据采集
   → GoldAPI.io    实时黄金价格
   → FRED          真实债券收益率、实际利率
   → NewsAPI       财经新闻标题

第 2 步：特征工程
   → 计算收益率（1h/4h/12h/24h）
   → 波动率、趋势状态
   → 宏观因子（美元、实际利率、收益率曲线）
   → 新闻情绪、事件强度
   → 市场状态（高波动/低波动、风险偏好、事件窗口）

第 3 步：保存快照
   → 写入 SQLite，关联 prompt / model / strategy 版本

第 4 步：LLM 市场分析（MiniMax M2.7）
   → 输入结构化特征 → 输出方向（看多/看空/中立）
   → 置信度 + 主要驱动因素 + 叙事

第 5 步：生成交易计划
   → 规则引擎确定立场（long / short / neutral）
   → LLM 提供叙事解释
   → 输出止损 / 止盈 / 风控建议
   → 写入数据库
```

**定时模式（`schedule-start`）**：每 4 小时自动跑一次，积累数据后用 `evaluate-pending` 评估预测准确率，用 `report-daily` / `report-weekly` 查看表现报表。

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
- 规则先于 LLM 做决策 — 模型负责研究归纳，规则负责交易决策
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

查看数据：
```bash
sqlite3 gold_trader.db ".schema"
sqlite3 gold_trader.db "SELECT id, status, xau_price, created_at FROM snapshots ORDER BY id DESC LIMIT 10;"
```

---

## 当前数据源配置

| 数据 | API | 注册地址 | 免费额度 |
|---|---|---|---|
| 黄金价格 | GoldAPI.io | goldapi.io | 100 请求/月 |
| 债券收益率 / TIPS | FRED | fred.stlouisfed.org | 免费 |
| 新闻 | NewsAPI.org | newsapi.org | 100 请求/天 |
| LLM | MiniMax M2.7 | platform.minimaxi.com | 按用量计费 |
| COT 持仓 | CFTC | cftc.gov | 免费（周更新） |

---

## 未来扩展方向

- [ ] COT 持仓数据接入（CFTC，免费）
- [ ] 回测引擎（基于历史数据）
- [ ] 多时间周期分析（15m、1h、4h、日线）
- [ ] 多品种支持（白银、矿业股、外汇）
- [ ] 告警通知（Slack、邮件）
- [ ] Web 控制台
- [ ] 多 Agent 架构（宏观分析师、技术分析师、情绪分析师）
- [ ] 策略 A/B 测试与集成学习

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
│   └─ weights.yaml          # 默认策略权重
├─ logs/                     # 日志文件（运行时创建）
├─ pyproject.toml
├─ .env.example
└─ README.md
```
