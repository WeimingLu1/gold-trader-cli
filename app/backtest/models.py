"""Backtest database models."""
from datetime import date, datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BacktestRun(Base):
    """Groups a set of backtest snapshots together."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="default")
    start_date: Mapped[date] = mapped_column(DateTime)
    end_date: Mapped[date] = mapped_column(DateTime)
    interval_hours: Mapped[int] = mapped_column(Integer, default=4)
    status: Mapped[str] = mapped_column(String(20), default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    snapshots: Mapped[list["BacktestSnapshot"]] = relationship(back_populates="run")


class BacktestSnapshot(Base):
    """
    A simulated snapshot created during a backtest run.

    as_of = the historical moment in time being simulated.
    """

    __tablename__ = "backtest_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    as_of: Mapped[datetime] = mapped_column(DateTime)
    horizon_hours: Mapped[int] = mapped_column(Integer, default=4)
    xau_price: Mapped[float] = mapped_column(Float)
    raw_features_json: Mapped[dict] = mapped_column(JSON)
    trade_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stance: Mapped[str] = mapped_column(String(20), default="neutral")
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    run: Mapped["BacktestRun"] = relationship(back_populates="snapshots")
    evaluation: Mapped["BacktestEvaluation | None"] = relationship(
        back_populates="snapshot", uselist=False
    )


class BacktestEvaluation(Base):
    """Post-hoc evaluation of a backtest snapshot."""

    __tablename__ = "backtest_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_snapshots.id"), unique=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    xau_price_at_horizon: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_actual: Mapped[str | None] = mapped_column(String(10), nullable=True)
    direction_hit: Mapped[bool | None] = mapped_column(nullable=True)
    stop_hit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    snapshot: Mapped["BacktestSnapshot"] = relationship(back_populates="evaluation")
