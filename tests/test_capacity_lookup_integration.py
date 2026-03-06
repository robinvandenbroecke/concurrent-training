"""
Sprint E2.1: Tests for capacity lookup integration into production strength impulse path.

Tests the canonical get_lift_capacity_estimate helper and its integration
into EngineOrchestrator._compute_strength_impulses.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.types import LiftType
from app.services.capacity_service import (
    get_lift_capacity_estimate,
    normalize_lift_type,
    LIFT_SPECIFIC_DEFAULTS,
)


class TestNormalizeLiftType:
    """Test lift type normalization for canonical lookup."""
    
    def test_enum_passes_through(self):
        """LiftType enum returns itself."""
        assert normalize_lift_type(LiftType.SQUAT) == LiftType.SQUAT
        assert normalize_lift_type(LiftType.BENCH) == LiftType.BENCH
    
    def test_string_lowercase_normalization(self):
        """String values normalize to canonical enum."""
        assert normalize_lift_type("squat") == LiftType.SQUAT
        assert normalize_lift_type("SQUAT") == LiftType.SQUAT
        assert normalize_lift_type("Squat") == LiftType.SQUAT
    
    def test_clean_aliases_normalized(self):
        """Clean/power clean aliases normalized to canonical types."""
        assert normalize_lift_type("clean") == LiftType.CLEAN
        assert normalize_lift_type("power_clean") == LiftType.POWER_CLEAN
        assert normalize_lift_type("power clean") == LiftType.POWER_CLEAN
        assert normalize_lift_type("POWER CLEAN") == LiftType.POWER_CLEAN
    
    def test_bench_aliases_normalized(self):
        """Bench press aliases normalized."""
        assert normalize_lift_type("bench") == LiftType.BENCH
        assert normalize_lift_type("bench_press") == LiftType.BENCH
        assert normalize_lift_type("bench press") == LiftType.BENCH
    
    def test_press_aliases_normalized(self):
        """Press aliases normalized."""
        assert normalize_lift_type("press") == LiftType.PRESS
        assert normalize_lift_type("overhead_press") == LiftType.PRESS
        assert normalize_lift_type("shoulder_press") == LiftType.PRESS
    
    def test_unknown_returns_other(self):
        """Unknown lift types return OTHER."""
        assert normalize_lift_type("unknown_lift") == LiftType.OTHER
        assert normalize_lift_type("curls") == LiftType.OTHER


class TestGetLiftCapacityEstimate:
    """Test canonical capacity lookup hierarchy."""
    
    def test_returns_capacity_profile_when_available(self, db_session, sample_athlete):
        """1) LiftCapacityProfile.model_capacity is preferred source."""
        from app.services.capacity_profile_service import CapacityProfileService
        from app.models import LiftCapacityProfile
        
        # Create capacity profile via service
        service = CapacityProfileService(db_session)
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=180,
            overwrite=True
        )
        
        # Update model capacity to a specific value
        profile = db_session.query(LiftCapacityProfile).filter(
            LiftCapacityProfile.athlete_id == sample_athlete.id,
            LiftCapacityProfile.lift == LiftType.SQUAT
        ).first()
        profile.model_capacity = 185.0
        db_session.commit()
        
        # Lookup should return capacity profile
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
        )
        
        assert capacity == 185.0
        assert source == "capacity_profile"
    
    def test_returns_day_state_when_no_profile(self, db_session, sample_athlete):
        """2) LiftDayState.C_l is used when no capacity profile exists."""
        from app.models import LiftDayState
        
        # Create lift day state with C_l
        lift_day_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.BENCH,
            date=date.today().isoformat(),
            D_l=10.0,
            F_l=1.0,
            C_l=105.0,  # Capacity
        )
        db_session.add(lift_day_state)
        db_session.commit()
        
        # Lookup should return day state capacity
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.BENCH,
        )
        
        assert capacity == 105.0
        assert source == "day_state"
    
    def test_returns_default_when_no_data(self, db_session, sample_athlete):
        """4) Lift-specific default is used when no profile or day state exists."""
        # Lookup for lift with no data
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.DEADLIFT,
        )
        
        assert capacity == LIFT_SPECIFIC_DEFAULTS[LiftType.DEADLIFT]  # 180.0
        assert source == "default"
    
    def test_default_values_per_lift(self, db_session, sample_athlete):
        """Default values are lift-specific."""
        test_cases = [
            (LiftType.SQUAT, 140.0),
            (LiftType.BENCH, 100.0),
            (LiftType.DEADLIFT, 180.0),
            (LiftType.PRESS, 70.0),
            (LiftType.POWER_CLEAN, 95.0),
            (LiftType.CLEAN, 95.0),
            (LiftType.OTHER, 100.0),
        ]
        
        for lift, expected_default in test_cases:
            capacity, source = get_lift_capacity_estimate(
                db=db_session,
                athlete_id=sample_athlete.id,
                lift=lift,
            )
            assert capacity == expected_default, f"Wrong default for {lift}"
            assert source == "default"
    
    def test_profile_takes_priority_over_day_state(self, db_session, sample_athlete):
        """Capacity profile is preferred over day state when both exist."""
        from app.services.capacity_profile_service import CapacityProfileService
        from app.models import LiftDayState
        
        # Create both profile and day state
        service = CapacityProfileService(db_session)
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=200,
            overwrite=True
        )
        
        # Update model capacity
        from app.models import LiftCapacityProfile
        profile = db_session.query(LiftCapacityProfile).filter(
            LiftCapacityProfile.athlete_id == sample_athlete.id,
            LiftCapacityProfile.lift == LiftType.SQUAT
        ).first()
        profile.model_capacity = 210.0
        
        # Create day state with different capacity
        lift_day_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            date=date.today().isoformat(),
            C_l=195.0,
        )
        db_session.add(lift_day_state)
        db_session.commit()
        
        # Should return profile value, not day state
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
        )
        
        assert capacity == 210.0
        assert source == "capacity_profile"
    
    def test_query_date_filters_day_states(self, db_session, sample_athlete):
        """Query date filters day states to on/before that date."""
        from app.models import LiftDayState
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Create day states for different dates
        old_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            date=yesterday.isoformat(),
            C_l=150.0,
        )
        new_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            date=today.isoformat(),
            C_l=160.0,
        )
        db_session.add_all([old_state, new_state])
        db_session.commit()
        
        # Query for yesterday should return old capacity
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            query_date=yesterday,
        )
        
        assert capacity == 150.0
    
    def test_invalid_capacity_uses_fallback(self, db_session, sample_athlete):
        """Invalid capacity values (<=0) fall through to next source."""
        from app.models import LiftDayState
        
        # Create day state with invalid C_l
        lift_day_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            date=date.today().isoformat(),
            C_l=0.0,  # Invalid
        )
        db_session.add(lift_day_state)
        db_session.commit()
        
        # Should fall through to default
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
        )
        
        assert source == "default"


class TestEngineOrchestratorIntegration:
    """Test integration of capacity lookup into EngineOrchestrator."""
    
    def test_compute_strength_impulses_uses_capacity_lookup(self, db_session, sample_athlete):
        """EngineOrchestrator uses capacity estimate for intensity calculation."""
        from app.services.engine_orchestrator import EngineOrchestrator
        from app.domain.rep_engine import SetInput, SessionInput, simulate_strength_session
        from app.models import LiftProfile
        
        # Use deadlift to avoid conflict with existing squat profile
        test_lift = LiftType.DEADLIFT
        
        # Check if profile exists first
        existing = db_session.query(LiftProfile).filter(
            LiftProfile.athlete_id == sample_athlete.id,
            LiftProfile.lift == test_lift
        ).first()
        
        if not existing:
            # Create lift profile
            lift_profile = LiftProfile(
                athlete_id=sample_athlete.id,
                lift=test_lift,
                a=0.50,
                b=0.0030,
            )
            db_session.add(lift_profile)
            db_session.commit()
        
        orchestrator = EngineOrchestrator(db_session)

        # Create a mock rep_output (minimal structure)
        sets_data = [
            {"load_kg": 140, "reps": 5},
        ]

        # Call _compute_strength_impulses with athlete context
        impulses = orchestrator._compute_strength_impulses(
            lift="deadlift",
            sets_data=sets_data,
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )

        # Should have computed impulses
        assert len(impulses.sets) == 1

        # Intensity should be based on default capacity (140kg / 180kg = 0.78)
        set_impulse = impulses.sets[0]
        expected_intensity = 140.0 / 180.0  # load / default capacity for deadlift
        assert set_impulse.intensity == pytest.approx(expected_intensity, abs=0.01)

        # Should have capacity metadata
        assert hasattr(impulses, '_capacity_estimate')
        assert hasattr(impulses, '_capacity_source')
    
    def test_intensity_clamping_applied(self, db_session, sample_athlete):
        """Intensity is clamped to [0.20, 1.20] range."""
        from app.services.engine_orchestrator import EngineOrchestrator
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Very light load should be clamped to min 0.20
        sets_data = [{"load_kg": 10, "reps": 5}]
        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        assert impulses.sets[0].intensity == pytest.approx(0.20, abs=0.01)
        
        # Very heavy load should be clamped to max 1.20
        sets_data = [{"load_kg": 1000, "reps": 1}]
        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=sets_data,
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        assert impulses.sets[0].intensity == pytest.approx(1.20, abs=0.01)
    
    def test_placeholder_comments_present(self, db_session, sample_athlete):
        """Placeholder TODO comments are present for velocity_factor and vl."""
        from app.services.engine_orchestrator import EngineOrchestrator
        import inspect
        
        # Check source code for TODO comments
        source = inspect.getsource(EngineOrchestrator._compute_strength_impulses)
        
        # Should contain TODO for Sprint E2.2
        assert "TODO(Sprint E2.2)" in source
        assert "velocity_factor" in source
        assert "vl" in source