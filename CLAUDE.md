# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**gold-trader-cli** is a **trading guidance system** (not an automated trading bot). It produces structured, explainable trading recommendations with full post-hoc performance evaluation.

Tech stack: Python 3.11+, Typer (CLI), SQLAlchemy 2.0, Pydantic v2, APScheduler, httpx, Loguru, Rich.

## Common Commands

```bash
# Development environment
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run a single test file
pytest tests/test_scorer.py -v

# Install in development mode
pip install -e ".[dev]"

# Lint with ruff
ruff check app/ tests/

# Initialize database
gold-cli init-db

# Run the full pipeline once
gold-cli run-once

# Start scheduled pipeline
gold-cli schedule-start

# Check system health
gold-cli doctor
```

## Architecture

```
collectors/   → Data collection (XAUUSD, bond yields, news, macro calendar)
features/     → Feature engineering (market, macro, news, regime features)
llm/          → LLM layer (Provider abstraction + Analyst + Planner)
strategy/     → Strategy layer (scorer, rules, risk management, weights)
evaluation/   → Post-hoc evaluation (evaluator, metrics, reports)
db/           → Database (SQLAlchemy ORM, SQLite by default)
scheduler/    → APScheduler-based scheduling
history/      → Historical data cache (yfinance gold, FRED rates) for backtesting
backtest/    → Historical backtest engine (BacktestEngine, models, metrics)
cli.py        → Typer CLI entrypoint (~31k lines, all commands)
```

## Backtest System (`gold-cli backtest`)

The backtest engine runs historical strategy simulation using real market data:

```bash
# Backtest Q1 2024
gold-cli backtest --start 2024-01-01 --end 2024-03-31 --interval 4

# Backtest with custom interval
gold-cli backtest --start 2026-02-01 --end 2026-02-28 --interval 4
```

Key modules:
- `app/history/gold.py` — GoldHistoryStore (yfinance GC=F, daily OHLCV)
- `app/history/rates.py` — RatesHistoryStore (FRED API, treasury yields + DXY)
- `app/history/cache.py` — SQLite-backed historical data cache
- `app/backtest/engine.py` — BacktestEngine (warm_cache → build snapshots → evaluate → metrics)
- `app/backtest/models.py` — BacktestRun, BacktestSnapshot, BacktestEvaluation ORM models
- `app/backtest/metrics.py` — compute_metrics (direction_hit_rate, sharpe, max_drawdown, by_stance, by_month)

## Core Pipeline (run-once)

```
Data Collection → Feature Building → LLM Analysis → Rule Scoring → Trade Plan → DB Record → Post-hoc Evaluation
```

1. **Collectors** fetch real data: XAUUSD (GoldAPI.io), Treasury yields (FRED), news (NewsAPI.org), macro calendar
2. **Features** compute 6 factors: USD, real rates, positioning, volatility, technical, news sentiment → composite score (-1.0 to +1.0)
3. **Analyst** (LLM) produces direction/confidence/narrative from structured features
4. **RuleEngine** maps composite score to stance (long/short/neutral) — rules override LLM decisions
5. **RiskManager** calculates stop-loss/take-profit (ATR-based)
6. **Planner** (LLM) generates narrative explanation for the trade plan
7. **Evaluator** runs after prediction horizon expires, comparing predicted vs actual direction

## Key Design Principles

- **Rules before LLM in decision-making**: The rule engine makes trading decisions; LLM only provides narrative explanation
- **All LLM output uses structured JSON schemas** (Pydantic models in `app/llm/schemas.py`)
- **Look-ahead bias prevention**: All data annotated with `available_time`
- **Provider abstraction**: `app/llm/provider.py` abstracts LLM API — mock provider available for development
- **Snapshot versioning**: Every recommendation records model version, prompt version, and strategy version

## Configuration

- `.env` — API keys, database URL, LLM settings, schedule interval
- `config/weights.yaml` — 6-factor strategy weights (sum must equal 1.0)
- Feature flags in `app/config.py`: `enable_rates`, `enable_news`, `enable_macro_calendar`, `enable_positioning`, `enable_etf_flows`

## Database

- SQLite by default: `gold_trader.db`
- Tables: `snapshots` (each recommendation), `evaluations` (post-hoc results), `model_versions`, `prompt_versions`, `strategy_versions`
- Use `gold-cli evaluate-pending` to evaluate matured predictions, `gold-cli report-daily` or `report-weekly` for reports

## Important File Locations

- CLI entrypoint: `app/cli.py`
- Feature snapshot model: `app/features/base.py` (FeatureSnapshot Pydantic model)
- Rule engine: `app/strategy/rules.py` (stance mapping + risk rules)
- Scoring engine: `app/strategy/scorer.py` (6-factor composite score)
- LLM provider: `app/llm/provider.py` (Mock + OpenAI-compatible)

## Known Issues & Improvement Areas

### Strategy Accuracy Calibration (High Priority)
- The rule thresholds (`LONG_THRESHOLD=0.25`, `SHORT_THRESHOLD=-0.25` in `app/strategy/rules.py`) are too conservative for trending markets.
- In strongly trending periods (e.g., gold bull runs), most scores fall within the neutral band, producing few actionable signals.
- **Fix**: Re-calibrate thresholds or use adaptive thresholds based on regime detection.
- Q1 2024 backtest: 33.3% direction accuracy; Feb 2026 backtest: 0% direction accuracy.

### Stop/TP Trigger Rate Very Low
- Stop-hit rate near 0% across all backtest periods — the ATR-based stop distances are too wide for the actual volatility.
- TP-hit rate also near 0% — TP distances too wide or horizon too short.
- **Fix**: Tighten ATR multiplier in `app/strategy/risk.py` or use regime-conditional multipliers.

### Intraday Historical Prices
- `_get_historical_prices` uses linear interpolation between daily closes — this is a rough approximation.
- In fast-moving markets (e.g., CPI releases), intraday price distribution is not linear.
- **Improvement**: Use hourly gold futures data from yfinance when available for more precise intraday features.

### DXY Previous-Day Value
- In backtest mode, `dxy_previous` defaults to `dxy_current` (0% change), degrading macro factor quality.
- **Fix**: Fetch previous day's DXY from cache during `warm_cache`.

### Weekend Gap Handling
- Weekend gaps (Friday close → Monday close) create large jumps that the linear intraday model can't capture.
- **Improvement**: Skip weekend bars in intraday feature computation, or use weekly bars as the primary timeframe for low-frequency signals.

### Data Completeness in Backtest
- News, COT, ETF flows are unavailable in backtest mode (set to 0/placeholder).
- This reduces `data_completeness` to ~62.5% and may affect confidence scoring.
- **Improvement**: Fetch news headlines retrospectively for backtest dates via news archive API.
