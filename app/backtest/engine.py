"""Backtest engine — runs historical strategy simulation."""
import json
import math
from datetime import date, datetime, timedelta
from collections import defaultdict

from app.config import get_settings
from app.features.base import FeatureSnapshot
from app.features.market_features import build_market_features
from app.features.macro_features import build_macro_features
from app.features.regime_features import build_regime_features
from app.strategy import DEFAULT_WEIGHTS
from app.strategy.scorer import Scorer
from app.strategy.rules import RuleEngine
from app.strategy.risk import RiskManager
from app.history.gold import GoldHistoryStore
from app.history.rates import RatesHistoryStore
from app.history.news import NewsHistoryStore
from app.backtest.models import BacktestRun, BacktestSnapshot, BacktestEvaluation, Base
from app.features.news_features import build_news_features_from_headlines
from app.db.session import get_engine, get_session_factory


class BacktestEngine:
    """
    Runs historical backtest for the gold trading strategy.

    Steps:
    1. warm_cache() — preload historical gold + rates data
    2. For each as_of timestamp in [start, end]:
         a. Build FeatureSnapshot using historical data
         b. Run Scorer → composite_score
         c. Run RuleEngine → stance
         d. Store BacktestSnapshot (status=pending)
    3. For each matured BacktestSnapshot:
         a. Fetch actual price at horizon
         b. Run Evaluator → BacktestEvaluation
    4. compute_metrics() → summary stats
    """

    def __init__(self):
        self.gold = GoldHistoryStore()
        self.rates = RatesHistoryStore()
        self.news = NewsHistoryStore()
        self.scorer = Scorer(DEFAULT_WEIGHTS)
        self.rules = RuleEngine()
        self.risk = RiskManager()
        self.session = get_session_factory()()
        self._ensure_tables()

    def _ensure_tables(self):
        Base.metadata.create_all(get_engine())

    def warm_cache(self, start_date: date, end_date: date) -> dict:
        """Pre-fetch all historical data into local cache."""
        gold_count = self.gold.warm_cache(start_date, end_date)
        rates_count = self.rates.warm_cache(start_date, end_date)
        news_count = self.news.warm_cache(start_date, end_date)
        return {"gold_bars": gold_count, "rates_bars": rates_count, "news_dates": news_count}

    def run(
        self,
        start_date: date,
        end_date: date,
        interval_hours: int = 4,
        name: str = "default",
    ) -> dict:
        """
        Execute full backtest run.

        Returns a dict with run info and metrics.
        """
        # Create backtest run record
        run = BacktestRun(
            name=name,
            start_date=start_date,
            end_date=end_date,
            interval_hours=interval_hours,
            status="running",
        )
        self.session.add(run)
        self.session.commit()

        # Warm cache first — extend by 7 days back to ensure previous trading day close is available
        cache_start = start_date - timedelta(days=7)
        cache_info = self.warm_cache(cache_start, end_date)

        # Generate as_of timestamps
        as_of_times = self._generate_timestamps(start_date, end_date, interval_hours)

        # Phase 1: Build snapshots
        snapshots = []
        skipped = 0
        for as_of in as_of_times:
            snap = self._build_backtest_snapshot(as_of, interval_hours, run.id)
            if snap:
                snapshots.append(snap)
            else:
                skipped += 1

        self.session.add_all(snapshots)
        self.session.commit()

        # Phase 2: Evaluate matured snapshots
        now = datetime.utcnow()
        evaluations = []
        for snap in snapshots:
            if snap.as_of + timedelta(hours=snap.horizon_hours) > now:
                continue  # not yet matured
            eval_result = self._evaluate_snapshot(snap)
            if eval_result:
                evaluations.append(eval_result)

        self.session.add_all(evaluations)
        run.status = "completed"
        self.session.commit()

        # Compute metrics
        from app.backtest.metrics import compute_metrics
        metrics = compute_metrics(snapshots, evaluations)

        return {
            "run_id": run.id,
            "name": name,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "interval_hours": interval_hours,
            "total_snapshots": len(snapshots),
            "skipped": skipped,
            "evaluated": len(evaluations),
            "cache": cache_info,
            "metrics": metrics,
        }

    def _generate_timestamps(
        self, start_date: date, end_date: date, interval_hours: int
    ) -> list[datetime]:
        """Generate list of as_of datetimes from start to end."""
        times = []
        current = datetime.combine(start_date, datetime.min.time()) + timedelta(hours=9, minutes=30)
        end = datetime.combine(end_date, datetime.min.time()) + timedelta(hours=23, minutes=59)
        step = timedelta(hours=interval_hours)
        while current <= end:
            times.append(current)
            current += step
        return times

    def _get_historical_prices(
        self, as_of: datetime, lookback_hours: int = 72
    ) -> dict[datetime, float]:
        """
        Build a dict of {datetime: price} for the lookback window ending at as_of.

        Uses daily gold bars from cache; intraday points are estimated by
        assuming price moves linearly within the day (for feature computation).

        Only uses bars from days strictly before as_of_date (the close of
        as_of_date is not yet known at as_of). Skips missing dates (weekends/holidays).
        """
        result: dict[datetime, float] = {}
        end_date = as_of.date()
        start_date = (as_of - timedelta(hours=lookback_hours)).date()

        cur = start_date
        prev_close = None
        while cur <= end_date:
            bar = self.gold.get_bar(cur)
            if bar:
                # Only use bars from days strictly before as_of_date
                if cur < end_date:
                    bar_dt = datetime.combine(cur, datetime.min.time()) + timedelta(hours=16)
                    result[bar_dt] = bar["close"]
                    if prev_close is not None:
                        # Fill in-between hours assuming linear drift
                        hourly_step = (bar["close"] - prev_close) / 24
                        for h in range(1, 24):
                            intra_dt = bar_dt - timedelta(hours=h)
                            if intra_dt not in result:
                                result[intra_dt] = bar["close"] - hourly_step * h
                    prev_close = bar["close"]
            cur += timedelta(days=1)
        return result

    def _build_backtest_snapshot(
        self, as_of: datetime, horizon_hours: int, run_id: int
    ) -> BacktestSnapshot | None:
        """
        Build a single backtest snapshot at as_of datetime.

        Returns None if essential data is missing (look-ahead prevention).
        """
        # Use the PREVIOUS trading day's close as the available price at as_of.
        # Gold's daily bar close (~16:00 ET) is only known after it happens.
        bar_date = as_of.date()
        gold_bar = self.gold.get_bar(bar_date)
        if not gold_bar:
            return None

        # For as_of times before the bar's close time, we can't use this bar.
        # Use previous trading day's bar instead.
        as_of_time_hrs = as_of.hour + as_of.minute / 60.0
        if as_of_time_hrs < 16.0:
            # Before today's close — use yesterday's bar
            prev_date = bar_date - timedelta(days=1)
            while prev_date.weekday() >= 5:  # skip weekend
                prev_date -= timedelta(days=1)
            prev_bar = self.gold.get_bar(prev_date)
            if prev_bar:
                gold_bar = prev_bar

        xau_price = gold_bar["close"]

        # Historical prices for returns/volatility
        hist_prices = self._get_historical_prices(as_of)
        fetched_at = as_of  # treat as_of as "fetched_at"
        market_feats = build_market_features(xau_price, hist_prices, fetched_at)

        # Macro features
        rates_bar = self.rates.get_bar(bar_date)
        if not rates_bar:
            rates_bar = {"dgs2": None, "dgs5": None, "dgs10": None, "dgs30": None, "dxy": None}
        dxy = rates_bar.get("dxy") or 104.5
        dxy_prev = dxy  # no previous available without cache warm
        dxy_change = (dxy - dxy_prev) / dxy_prev * 100 if dxy_prev else 0.0

        y10 = rates_bar.get("dgs10") or 4.38
        y10_prev = y10  # simplified
        y2 = rates_bar.get("dgs2") or 4.62
        y2_prev = y2
        y10_change = (y10 - y10_prev) * 100  # in bp
        real_rate = (y10 - 2.0) if y10 else 2.03  # rough

        macro_feats = build_macro_features(
            dxy_current=dxy,
            dxy_previous=dxy_prev,
            yield_10y_current=y10,
            yield_10y_previous=y10_prev,
            yield_2y_current=y2,
            yield_2y_previous=y2_prev,
            real_rate_proxy=real_rate,
        )

        # Regime (no macro calendar for backtest — simplified)
        regime_feats = build_regime_features(market_feats["volatility_24h"], [])

        # News features — use cached historical headlines.
        # Look-ahead safe: headlines from news_date are only used when as_of is on or after
        # that date AND after 16:00 ET (when same-day news is plausibly available).
        # Previous days' headlines are always safe to use.
        news_headlines: list[dict] = []
        news_date = gold_bar.get("date", bar_date.isoformat())
        if isinstance(news_date, str):
            news_date = date.fromisoformat(news_date)
        # Same-day headlines only available after market close (16:00)
        if as_of_time_hrs >= 16.0:
            news_headlines.extend(self.news.get_headlines(news_date))
        # Previous 3 trading days — always safe
        for offset in range(1, 4):
            prev_news_date = news_date - timedelta(days=offset)
            while prev_news_date.weekday() >= 5:  # skip weekends
                prev_news_date -= timedelta(days=1)
            prev_h = self.news.get_headlines(prev_news_date)
            news_headlines.extend(prev_h)
        news_feats = build_news_features_from_headlines(news_headlines)

        # Build FeatureSnapshot
        snapshot_at = as_of
        fs = FeatureSnapshot(
            snapshot_at=snapshot_at,
            xau_price=xau_price,
            xau_price_fetched_at=snapshot_at,
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
            cot_net_positions=0.0,
            etf_flow_24h=0.0,
            confidence_score=0.5,
            data_completeness=0.625,  # 5/8 sources (no DXY change, no news, no COT/ETF)
        )

        # Score
        composite_score, factor_scores = self.scorer.score(fs)

        # Rules
        stance, risk_note = self.rules.apply_risk_rules(
            self.rules.map_score_to_stance(
                composite_score, fs.confidence_score, fs.volatility_regime
            ),
            fs,
        )

        # Risk
        stop_pct = self.risk.compute_stop_distance(fs, horizon_hours)
        tp_pct = self.risk.compute_take_profit_distance(fs, horizon_hours)

        # Trade plan dict
        trade_plan = {
            "stance": stance,
            "horizon_hours": horizon_hours,
            "confidence": round(fs.confidence_score, 3),
            "composite_score": round(composite_score, 3),
            "stop_pct": round(stop_pct, 4),
            "tp_pct": round(tp_pct, 4),
            "risk_note": risk_note,
        }

        return BacktestSnapshot(
            backtest_run_id=run_id,
            as_of=as_of,
            horizon_hours=horizon_hours,
            xau_price=xau_price,
            raw_features_json=fs.model_dump(mode="json"),
            trade_plan_json=trade_plan,
            stance=stance,
            composite_score=round(composite_score, 4),
            confidence=round(fs.confidence_score, 3),
            status="pending",
            model_version="backtest-rule-based",
            prompt_version=None,
            strategy_version="v1.0",
        )

    def _evaluate_snapshot(self, snap: BacktestSnapshot) -> BacktestEvaluation | None:
        """Evaluate a matured backtest snapshot."""
        as_of = snap.as_of
        horizon_hours = snap.horizon_hours
        entry_price = snap.xau_price

        # Always use the close of the NEXT TRADING DAY as the horizon price.
        # This avoids same-day close issues (e.g., Sunday bar containing Friday's close).
        # The "close" of day D is recorded at ~16:00 ET on day D.
        next_date = as_of.date() + timedelta(days=1)
        while next_date.weekday() >= 5:  # skip weekend
            next_date += timedelta(days=1)

        horizon_bar = self.gold.get_bar(next_date)
        if not horizon_bar:
            # Fallback: scan forward up to 7 days
            for _ in range(7):
                next_date += timedelta(days=1)
                horizon_bar = self.gold.get_bar(next_date)
                if horizon_bar:
                    break
        if not horizon_bar:
            return None

        horizon_price = horizon_bar["close"]

        # Direction
        price_change_pct = (horizon_price - entry_price) / entry_price
        tolerance = 0.001  # 0.1%
        if price_change_pct > tolerance:
            direction_actual = "up"
        elif price_change_pct < -tolerance:
            direction_actual = "down"
        else:
            direction_actual = "flat"

        plan = snap.trade_plan_json or {}
        stance = plan.get("stance", "neutral")

        if stance == "neutral":
            direction_hit = None
        elif stance == "long":
            direction_hit = direction_actual == "up"
        elif stance == "short":
            direction_hit = direction_actual == "down"
        else:
            direction_hit = None

        # Stop/TP
        stop_hit = "neither"
        stop_pct = plan.get("stop_pct", 0.015)
        tp_pct = plan.get("tp_pct", 0.025)
        if stance == "long":
            stop_price = entry_price * (1 - stop_pct)
            tp_price = entry_price * (1 + tp_pct)
            if horizon_price >= tp_price:
                stop_hit = "tp"
            elif horizon_price <= stop_price:
                stop_hit = "stop"
        elif stance == "short":
            stop_price = entry_price * (1 + stop_pct)
            tp_price = entry_price * (1 - tp_pct)
            if horizon_price <= tp_price:
                stop_hit = "tp"
            elif horizon_price >= stop_price:
                stop_hit = "stop"

        # Returns
        actual_return = round(price_change_pct * 100, 4)
        expected_return = plan.get("tp_pct", 0.010) * 100

        # P&L
        pnl_pct = actual_return if stance == "long" else (-actual_return if stance == "short" else 0.0)

        return BacktestEvaluation(
            backtest_snapshot_id=snap.id,
            xau_price_at_horizon=horizon_price,
            direction_actual=direction_actual,
            direction_hit=direction_hit,
            stop_hit=stop_hit,
            expected_return=expected_return,
            actual_return=actual_return,
            pnl_pct=round(pnl_pct, 4),
        )
