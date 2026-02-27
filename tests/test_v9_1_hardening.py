"""
Sprint v9.1: PRODUCTION HARDENING tests

1. Strict T_legs roundtrip assertion
2. Concurrent/idempotency behavior tests  
3. Schema test for non-nullable content_hash
"""
import pytest
from datetime import date, datetime
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.types import LiftType, EnduranceSport
from app.services.engine_orchestrator import EngineOrchestrator
from app import models


class TestTLegsStrictRoundtrip:
    """Strict roundtrip assertion for T_legs persistence"""
    
    def test_t_legs_strict_roundtrip(self, db_session, sample_athlete):
        """
        v9.1: Strict T_legs roundtrip test.
        
        Steps:
        1. Ingest heavy legs session that changes T_legs from default
        2. Note T_legs value
        3. Reload in NEW DB session
        4. Assert abs(reloaded - stored) < 1e-9
        """
        from app.domain.day_engine import update_day_state, DayState, PerLiftState, DailyImpulses, StrengthImpulses, EnduranceImpulses, DayEngineParams
        from app.types import LiftType as DomainLiftType
        from app.domain.day_engine import EnduranceMode
        
        session_date = date(2024, 3, 1)
        
        # Create initial day state with T_legs = 0.0
        day_state = DayState(
            date=session_date,
            per_lift={
                "squat": PerLiftState(D_l=0.1, F_l=1.0, C_l=180.0),
                "bench": PerLiftState(D_l=0.05, F_l=1.0, C_l=100.0),
            },
            D_sys=0.1,
            R_mito=0.3,
            E_fat=0.0,
            T_legs=0.0  # Start at 0
        )
        
        # Create high-intensity legs impulse to increase T_legs
        impulses = DailyImpulses(
            strength=StrengthImpulses(
                per_lift={"squat": 2000.0},
                u_sys=2000.0,
                u_legs=2000.0,
                u_met=0.0,
                u_legs_high_intensity=1500.0,  # High intensity
                sets=[]
            ),
            endurance=EnduranceImpulses(
                u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0,
                mode=EnduranceMode.CYCLING, has_HIIT=False, has_Z2=False
            ),
            date=session_date
        )
        
        params = DayEngineParams()
        updated_day_state = update_day_state(day_state, impulses, params)
        
        # T_legs should have increased
        t_legs_after_update = updated_day_state.T_legs
        assert t_legs_after_update > 0.01, f"T_legs should increase from high-intensity legs work, got {t_legs_after_update}"
        
        # Persist to DB
        orchestrator = EngineOrchestrator(db_session)
        orchestrator._persist_day_state(sample_athlete.id, session_date, updated_day_state)
        db_session.commit()
        
        # Create NEW session to simulate reload
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.database import Base
        
        # Use same DB connection string as test
        engine = db_session.bind
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        new_session = TestingSessionLocal()
        try:
            # Reload via orchestrator in new session
            new_orchestrator = EngineOrchestrator(new_session)
            loaded_day_state = new_orchestrator.get_day_state_snapshot(sample_athlete.id, session_date)
            
            assert loaded_day_state is not None, "Day state should be reloadable"
            t_legs_reloaded = loaded_day_state.T_legs
            
            # Strict tolerance check
            tolerance = 1e-9
            assert abs(t_legs_reloaded - t_legs_after_update) < tolerance, \
                f"T_legs roundtrip failed: stored={t_legs_after_update}, reloaded={t_legs_reloaded}, diff={abs(t_legs_reloaded - t_legs_after_update)}"
        finally:
            new_session.close()


class TestConcurrentIdempotency:
    """Concurrency/idempotency behavior tests"""
    
    def test_strength_integrity_error_path(self, db_session, sample_athlete):
        """
        v9.1: Simulate duplicate insert by pre-inserting session with same hash.
        
        Steps:
        1. Pre-insert a session row with specific hash
        2. Call ingest with same data (will compute same hash)
        3. Assert idempotent flag is True and day_state unchanged
        """
        from datetime import datetime
        
        session_date = date(2024, 3, 10)
        sets_data = [
            {
                "load_kg": 100.0,
                "reps": 3,
                "velocities": [0.50, 0.48, 0.46],
                "rest_sec": 120.0
            }
        ]
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Compute hash for the session
        content_hash = orchestrator._compute_strength_content_hash(
            sample_athlete.id, session_date, "bench", sets_data, None
        )
        
        # Pre-insert session directly (simulating concurrent insert)
        pre_inserted = models.StrengthSession(
            athlete_id=sample_athlete.id,
            lift=LiftType.BENCH,
            start_time=datetime.combine(session_date, datetime.min.time()),
            content_hash=content_hash,
            tonnage=300.0,
            avg_intensity=0.70
        )
        db_session.add(pre_inserted)
        db_session.commit()
        
        # Get day state before second ingest
        day_state_before = orchestrator._get_or_create_day_state(sample_athlete.id, session_date)
        d_sys_before = day_state_before.D_sys
        
        # Now call ingest - should hit IntegrityError path
        result_session, result_day_state, snapshot = orchestrator.ingest_strength_session(
            athlete_id=sample_athlete.id,
            lift=LiftType.BENCH,
            session_date=session_date,
            sets_data=sets_data
        )
        
        # Assert idempotent response
        assert snapshot.get("idempotent") is True, "Should return idempotent=True"
        assert result_session.id == pre_inserted.id, "Should return pre-inserted session"
        assert result_day_state.D_sys == d_sys_before, "D_sys should not change (no double-apply)"
    
    def test_endurance_integrity_error_path(self, db_session, sample_athlete):
        """
        v9.1: Simulate duplicate insert for endurance session.
        """
        from datetime import datetime
        
        session_date = date(2024, 3, 11)
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Compute hash
        content_hash = orchestrator._compute_endurance_content_hash(
            sample_athlete.id, session_date, "cycling", 60.0, "z2", None
        )
        
        # Pre-insert session
        pre_inserted = models.EnduranceSession(
            athlete_id=sample_athlete.id,
            sport=EnduranceSport.CYCLING,
            start_time=datetime.combine(session_date, datetime.min.time()),
            content_hash=content_hash,
            duration_minutes=60.0,
            intensity_type="z2",
            u_E_Z2=60.0,
            u_E_HIIT=0.0
        )
        db_session.add(pre_inserted)
        db_session.commit()
        
        # Get state before
        day_state_before = orchestrator._get_or_create_day_state(sample_athlete.id, session_date)
        r_mito_before = day_state_before.R_mito
        
        # Call ingest - should hit IntegrityError
        result_session, result_day_state, snapshot = orchestrator.ingest_endurance_session(
            athlete_id=sample_athlete.id,
            session_date=session_date,
            sport=EnduranceSport.CYCLING,
            duration_minutes=60.0,
            intensity_type="z2"
        )
        
        # Assert idempotent
        assert snapshot.get("idempotent") is True, "Should return idempotent=True"
        assert result_session.id == pre_inserted.id, "Should return pre-inserted session"
        assert result_day_state.R_mito == r_mito_before, "R_mito should not change"
    
    def test_near_duplicate_creates_new_session(self, db_session, sample_athlete):
        """
        v9.1: Near duplicate (small velocity change) should create new session.
        """
        session_date = date(2024, 3, 12)
        
        orchestrator = EngineOrchestrator(db_session)
        
        # First session
        sets_data_1 = [
            {"load_kg": 100.0, "reps": 3, "velocities": [0.500, 0.480, 0.460], "rest_sec": 120.0}
        ]
        
        session1, _, _ = orchestrator.ingest_strength_session(
            sample_athlete.id, LiftType.BENCH, session_date, sets_data_1
        )
        db_session.commit()
        
        # Near duplicate - small velocity change
        sets_data_2 = [
            {"load_kg": 100.0, "reps": 3, "velocities": [0.501, 0.481, 0.461], "rest_sec": 120.0}
        ]
        
        session2, _, _ = orchestrator.ingest_strength_session(
            sample_athlete.id, LiftType.BENCH, session_date, sets_data_2
        )
        db_session.commit()
        
        # Different velocities = different hash = new session
        assert session1.id != session2.id, "Near duplicate should create new session"


class TestSchemaConstraints:
    """Schema tests for non-nullable content_hash"""
    
    def test_content_hash_not_nullable_strength(self, db_session):
        """
        v9.1: Verify content_hash column is non-nullable in StrengthSession.
        """
        from datetime import datetime
        
        session = models.StrengthSession(
            athlete_id=1,
            lift=LiftType.SQUAT,
            start_time=datetime.now(),
            # content_hash intentionally omitted
            tonnage=1000.0
        )
        db_session.add(session)
        
        # Should raise IntegrityError for NOT NULL constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        db_session.rollback()
    
    def test_content_hash_not_nullable_endurance(self, db_session):
        """
        v9.1: Verify content_hash column is non-nullable in EnduranceSession.
        """
        from datetime import datetime
        
        session = models.EnduranceSession(
            athlete_id=1,
            sport=EnduranceSport.RUNNING,
            start_time=datetime.now(),
            duration_minutes=30.0,
            intensity_type="z2"
            # content_hash intentionally omitted
        )
        db_session.add(session)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        db_session.rollback()
    
    def test_content_hash_column_metadata(self):
        """
        v9.1: Verify SQLAlchemy model metadata shows content_hash as non-nullable.
        """
        # Check StrengthSession
        strength_hash_col = models.StrengthSession.__table__.columns['content_hash']
        assert strength_hash_col.nullable is False, "StrengthSession.content_hash should be non-nullable"
        
        # Check EnduranceSession
        endurance_hash_col = models.EnduranceSession.__table__.columns['content_hash']
        assert endurance_hash_col.nullable is False, "EnduranceSession.content_hash should be non-nullable"
