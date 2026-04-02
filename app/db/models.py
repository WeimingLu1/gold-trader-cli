"""SQLAlchemy ORM models for the Gold Trader CLI."""
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, JSON, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class Snapshot(Base):
    """A single point-in-time snapshot of features, analyst output, and trade plan."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    horizon_hours: Mapped[int] = mapped_column(Integer, default=4)

    # Market data captured at snapshot time
    xau_price: Mapped[float] = mapped_column(Float)
    xau_price_fetched_at: Mapped[datetime] = mapped_column(DateTime)

    # Structured data captured
    raw_features_json: Mapped[dict] = mapped_column(JSON)
    analyst_output_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    trade_plan_json: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Lifecycle status: pending → matured → evaluated
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # Prompt / model / strategy version used
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(50), nullable=True)


class Evaluation(Base):
    """Post-hoc evaluation of a snapshot's trade plan against actual price outcomes."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column()
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Actual price at horizon
    xau_price_at_horizon: Mapped[float] = mapped_column(Float, nullable=True)
    direction_actual: Mapped[str] = mapped_column(String(10), nullable=True)  # up / down / flat

    # Outcome flags
    direction_hit: Mapped[bool] = mapped_column(Boolean, nullable=True)
    stop_hit: Mapped[str] = mapped_column(String(20), nullable=True)  # stop / tp / neither / pending
    expected_return: Mapped[float] = mapped_column(Float, nullable=True)
    actual_return: Mapped[float] = mapped_column(Float, nullable=True)

    # Versions used
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=True)
    strategy_version: Mapped[str] = mapped_column(String(50), nullable=True)

    notes: Mapped[str] = mapped_column(Text, nullable=True)


class ModelVersion(Base):
    """Registry of LLM model versions used in production."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=True)


class PromptVersion(Base):
    """Registry of analyst/planner prompt versions for reproducibility."""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    prompt_text: Mapped[str] = mapped_column(Text)


class StrategyVersion(Base):
    """Registry of strategy weight configurations."""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    weights_json: Mapped[dict] = mapped_column(JSON, nullable=True)
