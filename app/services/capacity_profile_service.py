"""
Sprint E3: Capacity Profile Service - Database integration layer

High-level service for managing lift capacity profiles with database persistence.
"""
from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.orm import Session

import app.models as db_models
from app.types import LiftType
from app.services.capacity_service import (
    initialize_lift_capacity,
    is_quality_strength_set,
    detect_breakthrough,
    CapacityInputType,
    CapacityConfidence,
    LIFT_DEFAULT_CAPACITY,
)


class CapacityProfileService:
    """Service for managing athlete lift capacity profiles."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_profile(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> db_models.LiftCapacityProfile:
        """
        Get existing capacity profile or create default.
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            LiftCapacityProfile (existing or newly created)
        """
        profile = self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id,
            db_models.LiftCapacityProfile.lift == lift
        ).first()
        
        if profile is None:
            # Create default profile with "unknown" input
            default_capacity = LIFT_DEFAULT_CAPACITY.get(lift, 80.0)
            
            profile = db_models.LiftCapacityProfile(
                athlete_id=athlete_id,
                lift=lift,
                input_type=CapacityInputType.UNKNOWN.value,
                input_load_kg=None,
                input_reps=None,
                input_rpe=None,
                anchor_capacity=default_capacity,
                model_capacity=default_capacity,
                confidence=CapacityConfidence.LOW.value,
                provisional_breakthrough_count=0,
                last_provisional_at=None,
                last_confirmed_breakthrough_at=None,
                last_signal_value=None,
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        
        return profile
    
    def get_profile(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> Optional[db_models.LiftCapacityProfile]:
        """
        Get capacity profile if it exists.
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            LiftCapacityProfile or None
        """
        return self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id,
            db_models.LiftCapacityProfile.lift == lift
        ).first()
    
    def get_all_profiles(
        self,
        athlete_id: int
    ) -> List[db_models.LiftCapacityProfile]:
        """
        Get all capacity profiles for an athlete.
        
        Args:
            athlete_id: Athlete ID
        
        Returns:
            List of LiftCapacityProfile
        """
        return self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id
        ).all()
    
    def initialize_from_input(
        self,
        athlete_id: int,
        lift: LiftType,
        input_type: str,  # "1rm", "best_set", "unknown"
        input_load_kg: Optional[float] = None,
        input_reps: Optional[int] = None,
        input_rpe: Optional[float] = None,
        overwrite: bool = False
    ) -> db_models.LiftCapacityProfile:
        """
        Initialize capacity profile from user input (onboarding).
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
            input_type: "1rm", "best_set", or "unknown"
            input_load_kg: Load in kg (for 1rm/best_set)
            input_reps: Reps (for best_set)
            input_rpe: RPE 6-10 (optional for best_set)
            overwrite: If True, overwrite existing profile
        
        Returns:
            Created/updated LiftCapacityProfile
        """
        existing = self.get_profile(athlete_id, lift)
        
        if existing and not overwrite:
            raise ValueError(
                f"Capacity profile already exists for athlete {athlete_id}, lift {lift.value}. "
                "Use overwrite=True to replace."
            )
        
        # Compute capacity from input
        init_result = initialize_lift_capacity(
            lift=lift,
            input_type=CapacityInputType(input_type),
            input_load_kg=input_load_kg,
            input_reps=input_reps,
            input_rpe=input_rpe
        )
        
        if existing:
            # Update existing
            existing.input_type = input_type
            existing.input_load_kg = input_load_kg
            existing.input_reps = input_reps
            existing.input_rpe = input_rpe
            existing.anchor_capacity = init_result.anchor_capacity
            existing.model_capacity = init_result.model_capacity
            existing.confidence = init_result.confidence.value
            # Reset breakthrough tracking on re-initialization
            existing.provisional_breakthrough_count = 0
            existing.last_provisional_at = None
            existing.last_signal_value = None
            profile = existing
        else:
            # Create new
            profile = db_models.LiftCapacityProfile(
                athlete_id=athlete_id,
                lift=lift,
                input_type=input_type,
                input_load_kg=input_load_kg,
                input_reps=input_reps,
                input_rpe=input_rpe,
                anchor_capacity=init_result.anchor_capacity,
                model_capacity=init_result.model_capacity,
                confidence=init_result.confidence.value,
                provisional_breakthrough_count=0,
                last_provisional_at=None,
                last_confirmed_breakthrough_at=None,
                last_signal_value=None,
            )
            self.db.add(profile)
        
        self.db.commit()
        self.db.refresh(profile)
        return profile
    
    def process_quality_set(
        self,
        athlete_id: int,
        lift: LiftType,
        load_kg: float,
        reps: int,
        rpe: Optional[float] = None,
        velocity_loss: Optional[float] = None
    ) -> Dict:
        """
        Process a strength set for capacity estimation.
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
            load_kg: Load in kg
            reps: Reps performed
            rpe: Optional RPE (6-10)
            velocity_loss: Optional velocity loss %
        
        Returns:
            Dict with quality result and breakthrough info
        """
        profile = self.get_or_create_profile(athlete_id, lift)
        
        # Check if this is a quality set
        quality_result = is_quality_strength_set(
            lift=lift,
            load_kg=load_kg,
            reps=reps,
            rpe=rpe,
            velocity_loss=velocity_loss,
            anchor_capacity=profile.anchor_capacity
        )
        
        if not quality_result.is_quality:
            return {
                "is_quality": False,
                "reason": quality_result.reason,
                "breakthrough": None
            }
        
        # Update last signal value
        profile.last_signal_value = quality_result.estimated_e1rm
        
        # Detect breakthrough
        breakthrough = detect_breakthrough(
            current_anchor=profile.anchor_capacity,
            current_model=profile.model_capacity,
            signal_e1rm=quality_result.estimated_e1rm,
            provisional_count=profile.provisional_breakthrough_count
        )
        
        result = {
            "is_quality": True,
            "estimated_e1rm": quality_result.estimated_e1rm,
            "quality_score": quality_result.quality_score,
            "breakthrough": {
                "is_provisional": breakthrough.is_provisional_breakthrough,
                "is_confirmed": breakthrough.is_confirmed_breakthrough,
                "signal_delta_pct": breakthrough.signal_delta_pct,
                "reason": breakthrough.reason
            }
        }
        
        # Update profile based on breakthrough result
        if breakthrough.is_confirmed_breakthrough:
            # Confirmed: update anchor and model
            profile.anchor_capacity = breakthrough.new_anchor_capacity
            profile.model_capacity = breakthrough.new_model_capacity
            profile.provisional_breakthrough_count = 0
            profile.last_confirmed_breakthrough_at = datetime.utcnow()
            profile.last_provisional_at = None
            profile.confidence = CapacityConfidence.HIGH.value
            result["breakthrough"]["new_anchor"] = breakthrough.new_anchor_capacity
            
        elif breakthrough.is_provisional_breakthrough:
            # Provisional: increment count, update model only
            profile.provisional_breakthrough_count += 1
            profile.model_capacity = breakthrough.new_model_capacity
            profile.last_provisional_at = datetime.utcnow()
            result["breakthrough"]["provisional_count"] = profile.provisional_breakthrough_count
            
        else:
            # No breakthrough: model drifts toward signal
            profile.model_capacity = breakthrough.new_model_capacity
            # Reset provisional count if signal drops below threshold
            if breakthrough.signal_delta_pct < 0:  # Performance declined
                profile.provisional_breakthrough_count = 0
        
        self.db.commit()
        self.db.refresh(profile)
        
        return result
    
    def get_model_capacity(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> float:
        """
        Get current model capacity for a lift (operational estimate).
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            Model capacity (kg)
        """
        profile = self.get_or_create_profile(athlete_id, lift)
        return profile.model_capacity
    
    def get_anchor_capacity(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> float:
        """
        Get current anchor capacity for a lift (stable reference).
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            Anchor capacity (kg)
        """
        profile = self.get_or_create_profile(athlete_id, lift)
        return profile.anchor_capacity
    
    def confirm_provisional_breakthrough(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> Optional[Dict]:
        """
        Manually confirm a provisional breakthrough.
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            Dict with result or None if no provisional breakthrough exists
        """
        profile = self.get_profile(athlete_id, lift)
        
        if not profile or profile.provisional_breakthrough_count == 0:
            return None
        
        if profile.last_signal_value is None:
            return None
        
        # Confirm breakthrough using last signal
        breakthrough = detect_breakthrough(
            current_anchor=profile.anchor_capacity,
            current_model=profile.model_capacity,
            signal_e1rm=profile.last_signal_value,
            provisional_count=profile.provisional_breakthrough_count - 1,  # Already counted
            confirmation_required_count=profile.provisional_breakthrough_count  # Force confirm
        )
        
        if breakthrough.is_confirmed_breakthrough:
            profile.anchor_capacity = breakthrough.new_anchor_capacity
            profile.model_capacity = breakthrough.new_model_capacity
            profile.provisional_breakthrough_count = 0
            profile.last_confirmed_breakthrough_at = datetime.utcnow()
            profile.last_provisional_at = None
            profile.confidence = CapacityConfidence.HIGH.value
            
            self.db.commit()
            self.db.refresh(profile)
            
            return {
                "confirmed": True,
                "new_anchor": profile.anchor_capacity,
                "previous_anchor": breakthrough.new_anchor_capacity / (1 + breakthrough.signal_delta_pct / 100),
                "improvement_pct": breakthrough.signal_delta_pct
            }
        
        return None
    
    def reset_provisional_breakthroughs(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> bool:
        """
        Reset provisional breakthrough count (e.g., if athlete believes they were fatigued).
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
        
        Returns:
            True if reset occurred, False if no profile exists
        """
        profile = self.get_profile(athlete_id, lift)
        
        if not profile:
            return False
        
        profile.provisional_breakthrough_count = 0
        profile.last_provisional_at = None
        
        self.db.commit()
        return True
