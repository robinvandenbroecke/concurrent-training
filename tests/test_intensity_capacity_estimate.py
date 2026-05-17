"""
Sprint E2.1: Required tests for intensity capacity estimate.

Tests verifying the capacity lookup integration produces correct intensities
for different lifts, athletes, and fallback scenarios.
"""
import pytest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from app.types import LiftType
from app.services.capacity_service import (
    get_lift_capacity_estimate,
    LIFT_SPECIFIC_DEFAULTS,
)
from app.services.engine_orchestrator import EngineOrchestrator


class TestSameLoadDifferentLifts:
    """Test 1: Same load for different lifts yields different intensities."""
    
    def test_100kg_squat_vs_bench_different_intensity(self, db_session, sample_athlete):
        """100kg squat vs 100kg bench must yield different intensities due to different defaults."""
        orchestrator = EngineOrchestrator(db_session)
        
        # 100kg squat (default capacity 140kg)
        squat_impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": 100, "reps": 5}],
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        squat_intensity = squat_impulses.sets[0].intensity
        expected_squat = 100.0 / 140.0  # ~0.714
        assert squat_intensity == pytest.approx(expected_squat, abs=0.01)
        
        # 100kg bench (default capacity 100kg)
        bench_impulses = orchestrator._compute_strength_impulses(
            lift="bench",
            sets_data=[{"load_kg": 100, "reps": 5}],
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        bench_intensity = bench_impulses.sets[0].intensity
        expected_bench = 100.0 / 100.0  # 1.0
        assert bench_intensity == pytest.approx(expected_bench, abs=0.01)
        
        # Bench intensity should be higher (same load, lower capacity)
        assert bench_intensity > squat_intensity


class TestSameLiftDifferentAthlete:
    """Test 2: Same lift and load for athletes with different capacities."""
    
    def test_different_athletes_same_lift_different_intensity(self, db_session, sample_athlete):
        """Athlete A with squat capacity 160 vs Athlete B with squat capacity 120."""
        from app.services.capacity_profile_service import CapacityProfileService
        
        # Create athlete A with capacity 160
        athlete_a = sample_athlete  # Use existing
        service_a = CapacityProfileService(db_session)
        service_a.initialize_from_input(
            athlete_id=athlete_a.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=160,
            overwrite=True
        )
        
        # Create athlete B with capacity 120
        from app.models import Athlete
        athlete_b = Athlete(name="Test Athlete B")
        db_session.add(athlete_b)
        db_session.flush()
        
        service_b = CapacityProfileService(db_session)
        service_b.initialize_from_input(
            athlete_id=athlete_b.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=120,
        )
        
        orchestrator = EngineOrchestrator(db_session)
        
        # Both athletes lift 100kg
        load_kg = 100
        
        # Athlete A intensity (100/160 = 0.625)
        impulses_a = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": load_kg, "reps": 5}],
            rep_output=None,
            athlete_id=athlete_a.id,
            session_date=date.today(),
        )
        intensity_a = impulses_a.sets[0].intensity
        assert intensity_a == pytest.approx(100.0 / 160.0, abs=0.01)
        
        # Athlete B intensity (100/120 = 0.833)
        impulses_b = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": load_kg, "reps": 5}],
            rep_output=None,
            athlete_id=athlete_b.id,
            session_date=date.today(),
        )
        intensity_b = impulses_b.sets[0].intensity
        assert intensity_b == pytest.approx(100.0 / 120.0, abs=0.01)
        
        # Athlete B (lower capacity) should have higher intensity for same load
        assert intensity_b > intensity_a


class TestLookupHierarchy:
    """Test 3-6: Verify capacity lookup hierarchy."""
    
    def test_prefers_capacity_profile_model_capacity(self, db_session, sample_athlete):
        """3) If LiftCapacityProfile exists, helper must use it first."""
        from app.services.capacity_profile_service import CapacityProfileService
        from app.models import LiftCapacityProfile
        
        # Create capacity profile with specific model_capacity
        service = CapacityProfileService(db_session)
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150,
            overwrite=True
        )
        
        # Update model capacity
        profile = db_session.query(LiftCapacityProfile).filter(
            LiftCapacityProfile.athlete_id == sample_athlete.id,
            LiftCapacityProfile.lift == LiftType.SQUAT
        ).first()
        profile.model_capacity = 175.0
        db_session.commit()
        
        # Lookup should return profile value
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
        )
        
        assert capacity == 175.0
        assert source == "capacity_profile"
    
    def test_falls_back_to_day_state_capacity(self, db_session, sample_athlete):
        """4) If no profile exists, use C_l from lift/day state."""
        from app.models import LiftDayState
        
        # Create day state with C_l
        lift_day_state = LiftDayState(
            athlete_id=sample_athlete.id,
            lift=LiftType.DEADLIFT,  # No profile exists for this lift
            date=date.today().isoformat(),
            D_l=5.0,
            F_l=1.0,
            C_l=195.0,
        )
        db_session.add(lift_day_state)
        db_session.commit()
        
        # Lookup should return day state capacity
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.DEADLIFT,
        )
        
        assert capacity == 195.0
        assert source == "day_state"
    
    def test_falls_back_to_performance_snapshot(self, db_session, sample_athlete):
        """5) If no profile and no day state, use latest performance estimate."""
        # Create a performance snapshot with e1rm estimate for press
        from app.models import PerformanceSnapshot
        
        snapshot = PerformanceSnapshot(
            athlete_id=sample_athlete.id,
            snapshot_date=date.today().isoformat(),
            days_analyzed=28,
            metrics_json={
                "lifts": {
                    "press": {
                        "e1rm_estimate": 65.0,
                        "trend": "maintain"
                    }
                }
            },
            overall_signal="maintain",
        )
        db_session.add(snapshot)
        db_session.commit()
        
        # Should now return performance estimate from snapshot
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.PRESS,
        )
        
        # Sprint E2.2: Performance lookup is now implemented
        assert source == "performance"
        assert capacity == 65.0
    
    def test_final_default_fallback(self, db_session, sample_athlete):
        """6) If nothing exists, return lift-specific default."""
        # Use a lift with no data
        capacity, source = get_lift_capacity_estimate(
            db=db_session,
            athlete_id=sample_athlete.id,
            lift=LiftType.POWER_CLEAN,
        )
        
        assert capacity == LIFT_SPECIFIC_DEFAULTS[LiftType.POWER_CLEAN]  # 95.0
        assert source == "default"


class TestProductionPathNoLongerUses200kg:
    """Test 7: Verify production path uses lookup, not hardcoded 200kg."""
    
    def test_production_path_uses_lookup_result(self, db_session, sample_athlete):
        """Directly test the production impulse path uses lookup result."""
        orchestrator = EngineOrchestrator(db_session)
        
        # With 200kg fallback, 100kg would give intensity = 0.5
        # With squat default (140kg), 100kg gives intensity = ~0.714
        load_kg = 100
        
        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": load_kg, "reps": 5}],
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        
        actual_intensity = impulses.sets[0].intensity
        
        # Should NOT be 0.5 (the old hardcoded 200kg behavior)
        assert actual_intensity != pytest.approx(0.5, abs=0.01)
        
        # Should be based on squat default (100/140 = ~0.714)
        expected_intensity = 100.0 / 140.0
        assert actual_intensity == pytest.approx(expected_intensity, abs=0.01)
    
    def test_no_hardcoded_200_in_production_code(self):
        """Verify no production code still contains load_kg / 200."""
        import os
        import re
        
        production_file = REPO_ROOT / "app" / "services" / "engine_orchestrator.py"
        
        with open(production_file, 'r') as f:
            content = f.read()
        
        # Check for the old pattern (allow in comments/tests)
        # The old pattern was: intensity = min(1.0, load_kg / 200)
        # This should NOT exist in the production code anymore
        
        # Remove comments
        code_without_comments = re.sub(r'#.*', '', content)
        
        # Check for load_kg / 200 pattern
        pattern = r'load_kg\s*/\s*200'
        matches = re.findall(pattern, code_without_comments)
        
        assert len(matches) == 0, f"Found hardcoded 200kg in production code: {matches}"
    
    def test_capacity_estimate_metadata_attached(self, db_session, sample_athlete):
        """Capacity estimate metadata is attached to impulses for verification."""
        orchestrator = EngineOrchestrator(db_session)
        
        impulses = orchestrator._compute_strength_impulses(
            lift="squat",
            sets_data=[{"load_kg": 100, "reps": 5}],
            rep_output=None,
            athlete_id=sample_athlete.id,
            session_date=date.today(),
        )
        
        # Should have capacity metadata
        assert hasattr(impulses, '_capacity_estimate')
        assert hasattr(impulses, '_capacity_source')
        
        # Capacity should not be 200 (the old fallback)
        assert impulses._capacity_estimate != 200.0
        
        # Should be the squat default
        assert impulses._capacity_estimate == 140.0
        assert impulses._capacity_source == "default"


class TestLiftSpecificDefaults:
    """Verify all lift-specific defaults are correct."""
    
    def test_all_lift_defaults(self, db_session, sample_athlete):
        """All lifts return correct default values."""
        expected = {
            LiftType.SQUAT: 140.0,
            LiftType.BENCH: 100.0,
            LiftType.DEADLIFT: 180.0,
            LiftType.PRESS: 70.0,
            LiftType.POWER_CLEAN: 95.0,
            LiftType.CLEAN: 95.0,
            LiftType.OTHER: 100.0,
        }
        
        for lift, expected_capacity in expected.items():
            capacity, source = get_lift_capacity_estimate(
                db=db_session,
                athlete_id=sample_athlete.id,
                lift=lift,
            )
            assert capacity == expected_capacity, f"Wrong default for {lift}"
            assert source == "default"