"""Repository layer for database operations."""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import Snapshot, Evaluation


class SnapshotRepo:
    """CRUD operations for Snapshot records."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        horizon_hours: int,
        xau_price: float,
        xau_price_fetched_at: datetime,
        raw_features: dict,
        prompt_version: str | None = None,
        model_version: str | None = None,
        strategy_version: str | None = None,
    ) -> Snapshot:
        snap = Snapshot(
            horizon_hours=horizon_hours,
            xau_price=xau_price,
            xau_price_fetched_at=xau_price_fetched_at,
            raw_features_json=raw_features,
            status="pending",
            prompt_version=prompt_version,
            model_version=model_version,
            strategy_version=strategy_version,
        )
        self.session.add(snap)
        self.session.commit()
        self.session.refresh(snap)
        return snap

    def update_analyst_output(self, snap_id: int, output: dict) -> None:
        snap = self.session.query(Snapshot).filter(Snapshot.id == snap_id).first()
        if snap:
            snap.analyst_output_json = output
            self.session.commit()

    def update_trade_plan(self, snap_id: int, plan: dict) -> None:
        snap = self.session.query(Snapshot).filter(Snapshot.id == snap_id).first()
        if snap:
            snap.trade_plan_json = plan
            self.session.commit()

    def get_by_id(self, snap_id: int) -> Optional[Snapshot]:
        return self.session.query(Snapshot).filter(Snapshot.id == snap_id).first()

    def get_pending(self) -> list[Snapshot]:
        return self.session.query(Snapshot).filter(Snapshot.status == "pending").all()

    def get_matured_pending(self, horizon_hours: int) -> list[Snapshot]:
        """Snapshots whose prediction window has elapsed but are still pending evaluation."""
        cutoff = datetime.utcnow() - timedelta(hours=horizon_hours)
        return (
            self.session.query(Snapshot)
            .filter(Snapshot.status == "pending")
            .filter(Snapshot.created_at < cutoff)
            .all()
        )

    def get_recent(self, limit: int = 50) -> list[Snapshot]:
        return (
            self.session.query(Snapshot)
            .order_by(Snapshot.created_at.desc())
            .limit(limit)
            .all()
        )

    def mark_matured(self, snap_id: int) -> None:
        snap = self.session.query(Snapshot).filter(Snapshot.id == snap_id).first()
        if snap:
            snap.status = "matured"
            self.session.commit()

    def mark_evaluated(self, snap_id: int) -> None:
        snap = self.session.query(Snapshot).filter(Snapshot.id == snap_id).first()
        if snap:
            snap.status = "evaluated"
            self.session.commit()


class EvaluationRepo:
    """CRUD operations for Evaluation records."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, snapshot_id: int, **kwargs) -> Evaluation:
        eval_ = Evaluation(snapshot_id=snapshot_id, **kwargs)
        self.session.add(eval_)
        self.session.commit()
        self.session.refresh(eval_)
        return eval_

    def get_by_snapshot(self, snapshot_id: int) -> Optional[Evaluation]:
        return (
            self.session.query(Evaluation)
            .filter(Evaluation.snapshot_id == snapshot_id)
            .first()
        )

    def get_recent(self, limit: int = 100) -> list[Evaluation]:
        return (
            self.session.query(Evaluation)
            .order_by(Evaluation.evaluated_at.desc())
            .limit(limit)
            .all()
        )

    def get_all_for_metrics(self) -> list[Evaluation]:
        return self.session.query(Evaluation).all()
