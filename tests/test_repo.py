"""Tests for repository layer using in-memory SQLite."""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Snapshot, Evaluation
from app.db.repo import SnapshotRepo, EvaluationRepo


@pytest.fixture
def engine():
    """In-memory SQLite engine for testing."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def test_snapshot_repo_create(session):
    """Test creating a snapshot."""
    repo = SnapshotRepo(session)
    snap = repo.create(
        horizon_hours=4,
        xau_price=2345.50,
        xau_price_fetched_at=datetime.utcnow(),
        raw_features={"test": "data"},
    )

    assert snap.id is not None
    assert snap.horizon_hours == 4
    assert snap.xau_price == 2345.50
    assert snap.status == "pending"


def test_snapshot_repo_update_analyst_output(session):
    """Test updating analyst output."""
    repo = SnapshotRepo(session)
    snap = repo.create(
        horizon_hours=4,
        xau_price=2345.50,
        xau_price_fetched_at=datetime.utcnow(),
        raw_features={},
    )

    repo.update_analyst_output(snap.id, {"direction": "bullish", "confidence": 0.7})
    updated = repo.get_by_id(snap.id)

    assert updated.analyst_output_json["direction"] == "bullish"


def test_snapshot_repo_get_matured_pending(session):
    """Test getting matured pending snapshots."""
    repo = SnapshotRepo(session)
    now = datetime.utcnow()

    # Create old snapshot (already matured — created 5 hours ago)
    old = Snapshot(
        horizon_hours=4,
        xau_price=2340.0,
        xau_price_fetched_at=now - timedelta(hours=5),
        raw_features_json={},
        status="pending",
        created_at=now - timedelta(hours=5),
    )
    session.add(old)

    # Create recent snapshot (not yet matured)
    recent = Snapshot(
        horizon_hours=4,
        xau_price=2345.0,
        xau_price_fetched_at=now,
        raw_features_json={},
        status="pending",
        created_at=now,
    )
    session.add(recent)
    session.commit()

    # Only old should be matured
    matured = repo.get_matured_pending(horizon_hours=4)
    assert len(matured) >= 1


def test_evaluation_repo_create(session):
    """Test creating an evaluation."""
    snap_repo = SnapshotRepo(session)
    snap = snap_repo.create(
        horizon_hours=4,
        xau_price=2345.0,
        xau_price_fetched_at=datetime.utcnow(),
        raw_features={},
    )

    eval_repo = EvaluationRepo(session)
    ev = eval_repo.create(
        snapshot_id=snap.id,
        xau_price_at_horizon=2350.0,
        direction_actual="up",
        direction_hit=True,
        expected_return=1.5,
        actual_return=1.7,
    )

    assert ev.id is not None
    assert ev.direction_hit is True
    assert ev.actual_return == 1.7
