"""
Sprint V1.1: Replay determinism tests

Ensures ReplayRunner produces identical outputs for identical inputs.
"""
import pytest
import tempfile
import json
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.eval.replay import ReplayRunner
from app import models
from app.types import LiftType, EnduranceSport


class TestReplayDeterminism:
    """Test that replay produces deterministic outputs."""
    
    @pytest.fixture
    def test_db(self):
        """Create a temporary test database with sample data."""
        # Create temp file for SQLite
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        engine = create_engine(f"sqlite:///{db_path}")
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
            os.unlink(db_path)
    
    def test_replay_produces_identical_summaries(self, test_db):
        """
        Running replay twice with same inputs must produce identical summary.json.
        
        Steps:
        1. Create athlete with sample sessions
        2. Run replay twice to different output dirs
        3. Compare summary.json byte-for-byte
        """
        # Setup test data
        athlete = models.Athlete(name="Test Athlete")
        test_db.add(athlete)
        test_db.commit()
        test_db.refresh(athlete)
        
        # Create lift profile
        profile = models.LiftProfile(
            athlete_id=athlete.id,
            lift=LiftType.SQUAT,
            a=0.55,
            b=0.0032
        )
        test_db.add(profile)
        
        # Create strength session with VBT data
        strength_session = models.StrengthSession(
            athlete_id=athlete.id,
            lift=LiftType.SQUAT,
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            content_hash="abc123def456",
            tonnage=1500.0,
            avg_intensity=0.75,
            raw_data={
                "sets": [
                    {
                        "weight": 100.0,
                        "reps": [
                            {"velocity": 0.50, "rep_num": 1, "rest_before": 180},
                            {"velocity": 0.48, "rep_num": 2, "rest_before": 3},
                            {"velocity": 0.46, "rep_num": 3, "rest_before": 3},
                        ]
                    },
                    {
                        "weight": 100.0,
                        "reps": [
                            {"velocity": 0.47, "rep_num": 1, "rest_before": 240},
                            {"velocity": 0.44, "rep_num": 2, "rest_before": 3},
                            {"velocity": 0.42, "rep_num": 3, "rest_before": 3},
                        ]
                    }
                ],
                "final_A_local": {"squat": 0.85},
                "final_A_sys": 0.90,
            }
        )
        test_db.add(strength_session)
        
        # Create endurance session
        endurance_session = models.EnduranceSession(
            athlete_id=athlete.id,
            sport=EnduranceSport.CYCLING,
            start_time=datetime(2024, 1, 16, 8, 0, 0),
            content_hash="def789abc012",
            duration_minutes=60.0,
            intensity_type="z2",
            u_E_Z2=60.0,
            u_E_HIIT=0.0
        )
        test_db.add(endurance_session)
        
        # Create day state
        day_state = models.DayState(
            athlete_id=athlete.id,
            date="2024-01-15",
            D_sys=0.1,
            R_mito=0.2,
            E_fat=0.0,
            T_legs=0.15
        )
        test_db.add(day_state)
        
        # Create per-lift day state
        lift_day_state = models.LiftDayState(
            athlete_id=athlete.id,
            lift=LiftType.SQUAT,
            date="2024-01-15",
            D_l=0.15,
            F_l=1.0,
            C_l=150.0
        )
        test_db.add(lift_day_state)
        
        test_db.commit()
        
        # Run replay twice
        with tempfile.TemporaryDirectory() as tmpdir:
            run1_dir = Path(tmpdir) / "run1"
            run2_dir = Path(tmpdir) / "run2"
            
            # First run
            runner1 = ReplayRunner(test_db, artifacts_dir=str(run1_dir))
            report1 = runner1.replay(
                athlete_id=athlete.id,
                date_from=date(2024, 1, 1),
                date_to=date(2024, 1, 31),
                dry_run=True
            )
            runner1.write_artifacts("test_run")
            
            # Second run
            runner2 = ReplayRunner(test_db, artifacts_dir=str(run2_dir))
            report2 = runner2.replay(
                athlete_id=athlete.id,
                date_from=date(2024, 1, 1),
                date_to=date(2024, 1, 31),
                dry_run=True
            )
            runner2.write_artifacts("test_run")
            
            # Compare summary.json files
            summary1_path = run1_dir / "test_run" / "summary.json"
            summary2_path = run2_dir / "test_run" / "summary.json"
            
            assert summary1_path.exists(), "summary.json should exist after first run"
            assert summary2_path.exists(), "summary.json should exist after second run"
            
            with open(summary1_path) as f:
                content1 = f.read()
            with open(summary2_path) as f:
                content2 = f.read()
            
            # Byte-for-byte comparison
            assert content1 == content2, f"Summary files differ:\n{content1[:200]}...\nvs\n{content2[:200]}..."
            
            # Also compare parsed content for safety
            data1 = json.loads(content1)
            data2 = json.loads(content2)
            assert data1 == data2, "Parsed summary data should be identical"
    
    def test_replay_metrics_are_deterministic(self, test_db):
        """
        Key metrics should be identical across runs.
        """
        # Setup same as above
        athlete = models.Athlete(name="Test Athlete 2")
        test_db.add(athlete)
        test_db.commit()
        test_db.refresh(athlete)
        
        profile = models.LiftProfile(
            athlete_id=athlete.id,
            lift=LiftType.BENCH,
            a=0.60,
            b=0.0028
        )
        test_db.add(profile)
        
        # Create multiple sessions
        for i in range(3):
            session = models.StrengthSession(
                athlete_id=athlete.id,
                lift=LiftType.BENCH,
                start_time=datetime(2024, 2, 1 + i, 10, 0, 0),
                content_hash=f"hash{i}abc123",
                tonnage=1200.0,
                avg_intensity=0.70,
                raw_data={
                    "sets": [{
                        "weight": 80.0,
                        "reps": [
                            {"velocity": 0.55, "rep_num": 1},
                            {"velocity": 0.52, "rep_num": 2},
                        ]
                    }],
                    "final_A_local": {"bench": 0.90},
                    "final_A_sys": 0.92,
                }
            )
            test_db.add(session)
        
        lift_ds = models.LiftDayState(
            athlete_id=athlete.id,
            lift=LiftType.BENCH,
            date="2024-02-01",
            D_l=0.1,
            F_l=1.0,
            C_l=100.0
        )
        test_db.add(lift_ds)
        test_db.commit()
        
        # Run twice and compare metrics
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_list = []
            
            for run_num in range(2):
                run_dir = Path(tmpdir) / f"run{run_num}"
                runner = ReplayRunner(test_db, artifacts_dir=str(run_dir))
                report = runner.replay(
                    athlete_id=athlete.id,
                    date_from=date(2024, 2, 1),
                    date_to=date(2024, 2, 28),
                    dry_run=True
                )
                runner.write_artifacts("test")
                
                # Read summary
                summary_path = run_dir / "test" / "summary.json"
                with open(summary_path) as f:
                    summary = json.load(f)
                
                metrics_list.append(summary)
            
            # Compare key metrics
            assert metrics_list[0]["n_rep_errors"] == metrics_list[1]["n_rep_errors"]
            assert metrics_list[0]["n_day_errors"] == metrics_list[1]["n_day_errors"]
            
            if metrics_list[0]["rep_metrics"]:
                assert (
                    metrics_list[0]["rep_metrics"]["rmse"] == 
                    metrics_list[1]["rep_metrics"]["rmse"]
                )
                assert (
                    metrics_list[0]["rep_metrics"]["mae"] == 
                    metrics_list[1]["rep_metrics"]["mae"]
                )


import os
