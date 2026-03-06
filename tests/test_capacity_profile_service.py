"""
Tests for Sprint E3: Capacity Profile Service (database integration)
"""
import pytest
from datetime import datetime

from app.types import LiftType
from app.services.capacity_profile_service import CapacityProfileService
from app.services.capacity_service import CapacityConfidence, CapacityInputType
import app.models as db_models


class TestCapacityProfileService:
    """Test CapacityProfileService database operations"""
    
    def test_get_or_create_profile_creates_default(self, db_session, sample_athlete):
        """get_or_create_profile creates default profile if none exists"""
        service = CapacityProfileService(db_session)
        
        profile = service.get_or_create_profile(sample_athlete.id, LiftType.SQUAT)
        
        assert profile is not None
        assert profile.athlete_id == sample_athlete.id
        assert profile.lift == LiftType.SQUAT
        assert profile.input_type == CapacityInputType.UNKNOWN.value
        assert profile.anchor_capacity == 100.0  # Default for squat
        assert profile.model_capacity == 100.0
        assert profile.confidence == CapacityConfidence.LOW.value
    
    def test_get_or_create_profile_returns_existing(self, db_session, sample_athlete):
        """get_or_create_profile returns existing profile if present"""
        service = CapacityProfileService(db_session)
        
        # Create initial profile
        profile1 = service.get_or_create_profile(sample_athlete.id, LiftType.BENCH)
        original_id = profile1.id
        
        # Call again - should return same profile
        profile2 = service.get_or_create_profile(sample_athlete.id, LiftType.BENCH)
        
        assert profile2.id == original_id
        assert profile1.anchor_capacity == profile2.anchor_capacity
    
    def test_get_profile_returns_none_if_not_exists(self, db_session, sample_athlete):
        """get_profile returns None if profile doesn't exist"""
        service = CapacityProfileService(db_session)
        
        profile = service.get_profile(sample_athlete.id, LiftType.DEADLIFT)
        
        assert profile is None
    
    def test_get_profile_returns_existing(self, db_session, sample_athlete):
        """get_profile returns existing profile"""
        service = CapacityProfileService(db_session)
        
        # Create profile
        service.get_or_create_profile(sample_athlete.id, LiftType.PRESS)
        
        # Get it
        profile = service.get_profile(sample_athlete.id, LiftType.PRESS)
        
        assert profile is not None
        assert profile.lift == LiftType.PRESS
    
    def test_get_all_profiles_empty(self, db_session, sample_athlete):
        """get_all_profiles returns empty list if no profiles"""
        service = CapacityProfileService(db_session)
        
        profiles = service.get_all_profiles(sample_athlete.id)
        
        assert profiles == []
    
    def test_get_all_profiles_multiple(self, db_session, sample_athlete):
        """get_all_profiles returns all profiles for athlete"""
        service = CapacityProfileService(db_session)
        
        # Create multiple profiles
        service.get_or_create_profile(sample_athlete.id, LiftType.SQUAT)
        service.get_or_create_profile(sample_athlete.id, LiftType.BENCH)
        service.get_or_create_profile(sample_athlete.id, LiftType.DEADLIFT)
        
        profiles = service.get_all_profiles(sample_athlete.id)
        
        assert len(profiles) == 3
        lifts = [p.lift for p in profiles]
        assert LiftType.SQUAT in lifts
        assert LiftType.BENCH in lifts
        assert LiftType.DEADLIFT in lifts
    
    def test_initialize_from_input_1rm(self, db_session, sample_athlete):
        """initialize_from_input creates profile from 1RM"""
        service = CapacityProfileService(db_session)
        
        profile = service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150
        )
        
        assert profile.anchor_capacity == 150
        assert profile.model_capacity == 150
        assert profile.confidence == CapacityConfidence.HIGH.value
        assert profile.input_type == "1rm"
        assert profile.input_load_kg == 150
    
    def test_initialize_from_input_best_set(self, db_session, sample_athlete):
        """initialize_from_input creates profile from best set"""
        service = CapacityProfileService(db_session)

        profile = service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.BENCH,
            input_type="best_set",
            input_load_kg=100,
            input_reps=5,
            input_rpe=8
        )

        # With RPE 8: adjusted_reps = 5 + (10-8) = 7, so e1RM = 100 * (1 + 7/30) = 123.33
        expected_e1rm = 100 * (1 + 7/30)
        assert profile.anchor_capacity == pytest.approx(expected_e1rm, rel=1e-3)
        assert profile.input_load_kg == 100
        assert profile.input_reps == 5
        assert profile.input_rpe == 8
    
    def test_initialize_from_input_unknown(self, db_session, sample_athlete):
        """initialize_from_input creates profile with defaults"""
        service = CapacityProfileService(db_session)
        
        profile = service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.DEADLIFT,
            input_type="unknown"
        )
        
        assert profile.anchor_capacity == 120.0  # Default for deadlift
        assert profile.confidence == CapacityConfidence.LOW.value
    
    def test_initialize_raises_if_exists(self, db_session, sample_athlete):
        """initialize_from_input raises if profile exists and overwrite=False"""
        service = CapacityProfileService(db_session)
        
        # Create initial profile
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150
        )
        
        # Try to create again without overwrite
        with pytest.raises(ValueError, match="already exists"):
            service.initialize_from_input(
                athlete_id=sample_athlete.id,
                lift=LiftType.SQUAT,
                input_type="1rm",
                input_load_kg=160
            )
    
    def test_initialize_with_overwrite(self, db_session, sample_athlete):
        """initialize_from_input overwrites if overwrite=True"""
        service = CapacityProfileService(db_session)
        
        # Create initial profile
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150
        )
        
        # Overwrite with new value
        profile = service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=160,
            overwrite=True
        )
        
        assert profile.anchor_capacity == 160
    
    def test_process_quality_set_not_quality(self, db_session, sample_athlete):
        """process_quality_set handles non-quality sets"""
        service = CapacityProfileService(db_session)
        
        # Initialize with 200kg anchor
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=200
        )
        
        # Try to process light set (below 70% threshold)
        result = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=100,  # Only 50% of anchor
            reps=5,
            rpe=8
        )
        
        assert result["is_quality"] is False
        assert "breakthrough" in result
    
    def test_process_quality_set_provisional_breakthrough(self, db_session, sample_athlete):
        """process_quality_set detects provisional breakthrough"""
        service = CapacityProfileService(db_session)
        
        # Initialize with 100kg anchor
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=100
        )
        
        # Process quality set indicating ~103.1kg capacity (3.1% increase)
        # Above 2.5% threshold for provisional, below 4% for immediate confirmation
        # 91kg x 3 @ RPE 9: e1RM = 91 * (1 + 4/30) = 91 * 1.133 = 103.1
        result = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=91,
            reps=3,
            rpe=9
        )

        assert result["is_quality"] is True
        assert result["breakthrough"]["is_provisional"] is True
        assert result["breakthrough"]["is_confirmed"] is False
        
        # Verify profile updated
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.provisional_breakthrough_count == 1
    
    def test_process_quality_set_confirmed_breakthrough(self, db_session, sample_athlete):
        """process_quality_set confirms breakthrough after 2 signals"""
        service = CapacityProfileService(db_session)
        
        # Initialize
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=100
        )
        
        # First signal (provisional) - ~3.3% increase
        service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=100,
            reps=3,
            rpe=9
        )

        # Second signal (should confirm) - another ~3.3% increase
        result = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=101,
            reps=3,
            rpe=9
        )

        assert result["breakthrough"]["is_confirmed"] is True

        # Verify profile updated
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.provisional_breakthrough_count == 0
        assert profile.anchor_capacity > 100  # Anchor updated
    
    def test_get_model_capacity(self, db_session, sample_athlete):
        """get_model_capacity returns operational estimate"""
        service = CapacityProfileService(db_session)
        
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150
        )
        
        capacity = service.get_model_capacity(sample_athlete.id, LiftType.SQUAT)
        
        assert capacity == 150
    
    def test_get_anchor_capacity(self, db_session, sample_athlete):
        """get_anchor_capacity returns stable reference"""
        service = CapacityProfileService(db_session)
        
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=150
        )
        
        capacity = service.get_anchor_capacity(sample_athlete.id, LiftType.SQUAT)
        
        assert capacity == 150
    
    def test_confirm_provisional_breakthrough(self, db_session, sample_athlete):
        """confirm_provisional_breakthrough manually confirms"""
        service = CapacityProfileService(db_session)
        
        # Initialize and create provisional
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=100
        )
        
        service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=91,  # ~3.1% increase, provisional but not confirmed
            reps=3,
            rpe=9
        )

        # Verify provisional was created
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.provisional_breakthrough_count == 1

        # Manually confirm
        result = service.confirm_provisional_breakthrough(sample_athlete.id, LiftType.SQUAT)

        assert result is not None
        assert result["confirmed"] is True
        assert result["new_anchor"] > 100
    
    def test_confirm_provisional_no_provisional(self, db_session, sample_athlete):
        """confirm_provisional_breakthrough returns None if no provisional"""
        service = CapacityProfileService(db_session)
        
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=100
        )
        
        result = service.confirm_provisional_breakthrough(sample_athlete.id, LiftType.SQUAT)
        
        assert result is None
    
    def test_reset_provisional_breakthroughs(self, db_session, sample_athlete):
        """reset_provisional_breakthroughs clears count"""
        service = CapacityProfileService(db_session)
        
        # Initialize and create provisional
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=100
        )
        
        service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=91,  # ~3.1% increase, provisional but not confirmed
            reps=3,
            rpe=9
        )

        # Verify provisional exists
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.provisional_breakthrough_count == 1
        
        # Reset
        success = service.reset_provisional_breakthroughs(sample_athlete.id, LiftType.SQUAT)
        
        assert success is True
        
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.provisional_breakthrough_count == 0
        assert profile.last_provisional_at is None
    
    def test_reset_provisional_no_profile(self, db_session, sample_athlete):
        """reset_provisional_breakthroughs returns False if no profile"""
        service = CapacityProfileService(db_session)
        
        success = service.reset_provisional_breakthroughs(sample_athlete.id, LiftType.SQUAT)
        
        assert success is False


class TestCapacityProfileIntegration:
    """Integration tests for capacity profile workflow"""
    
    def test_full_onboarding_workflow(self, db_session, sample_athlete):
        """Complete onboarding workflow for multiple lifts"""
        service = CapacityProfileService(db_session)
        
        # Onboard with 1RM for main lifts
        lifts_data = [
            (LiftType.SQUAT, "1rm", 150, None, None),
            (LiftType.BENCH, "best_set", 100, 5, 8),
            (LiftType.DEADLIFT, "unknown", None, None, None),
        ]
        
        for lift, input_type, load, reps, rpe in lifts_data:
            profile = service.initialize_from_input(
                athlete_id=sample_athlete.id,
                lift=lift,
                input_type=input_type,
                input_load_kg=load,
                input_reps=reps,
                input_rpe=rpe
            )
            
            assert profile is not None
            assert profile.confidence in [c.value for c in CapacityConfidence]
        
        # Verify all profiles created
        profiles = service.get_all_profiles(sample_athlete.id)
        assert len(profiles) == 3
    
    def test_training_with_breakthrough_detection(self, db_session, sample_athlete):
        """Simulate training with breakthrough detection"""
        service = CapacityProfileService(db_session)

        # Start with 200kg squat (higher to give more room)
        service.initialize_from_input(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            input_type="1rm",
            input_load_kg=200
        )

        # Week 1: Normal training (no breakthrough)
        # 150kg x 5 @ RPE 8: adjusted_reps = 5 + 2 = 7, e1RM = 150 * 1.233 = 185 < 200
        result1 = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=150,  # 75% of 200 (minimum for quality)
            reps=5,
            rpe=8
        )
        assert result1["breakthrough"]["is_provisional"] is False

        # Week 2: Strong session (provisional)
        # 182kg x 3 @ RPE 9: adjusted_reps = 4, e1RM = 182 * 1.133 = 206.2 (~3.1% increase)
        # Above 2.5% threshold for provisional, below 4% for immediate confirmation
        result2 = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=182,
            reps=3,
            rpe=9
        )
        assert result2["breakthrough"]["is_provisional"] is True
        assert result2["breakthrough"]["is_confirmed"] is False

        # Week 3: Another strong session (confirmed)
        result3 = service.process_quality_set(
            athlete_id=sample_athlete.id,
            lift=LiftType.SQUAT,
            load_kg=183,  # Similar signal to confirm
            reps=3,
            rpe=9
        )
        assert result3["breakthrough"]["is_confirmed"] is True

        # Verify anchor updated
        profile = service.get_profile(sample_athlete.id, LiftType.SQUAT)
        assert profile.anchor_capacity > 200
        assert profile.confidence == CapacityConfidence.HIGH.value
