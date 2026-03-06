"""
Sprint E3 Refined: Capacity Profile Service - Database integration layer

High-level service for managing lift capacity profiles with refined breakthrough logic.
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

import app.models as db_models
from app.types import LiftType
from app.services.capacity_service import (
    initialize_lift_capacity,
    is_quality_strength_set,
    detect_breakthrough_v2,
    extract_strength_performance_signal,
    update_model_capacity,
    apply_confirmed_breakthrough,
    CapacityInputType,
    CapacityConfidence,
    LIFT_DEFAULT_CAPACITY,
    PROVISIONAL_WINDOW_DAYS,
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
        """Get existing capacity profile or create default."""
        profile = self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id,
            db_models.LiftCapacityProfile.lift == lift
        ).first()
        
        if profile is None:
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
        """Get capacity profile if it exists."""
        return self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id,
            db_models.LiftCapacityProfile.lift == lift
        ).first()
    
    def get_all_profiles(
        self,
        athlete_id: int
    ) -> List[db_models.LiftCapacityProfile]:
        """Get all capacity profiles for an athlete."""
        return self.db.query(db_models.LiftCapacityProfile).filter(
            db_models.LiftCapacityProfile.athlete_id == athlete_id
        ).all()
    
    def initialize_from_input(
        self,
        athlete_id: int,
        lift: LiftType,
        input_type: str,
        input_load_kg: Optional[float] = None,
        input_reps: Optional[int] = None,
        input_rpe: Optional[float] = None,
        overwrite: bool = False
    ) -> db_models.LiftCapacityProfile:
        """Initialize capacity profile from user input (onboarding)."""
        existing = self.get_profile(athlete_id, lift)
        
        if existing and not overwrite:
            raise ValueError(
                f"Capacity profile already exists for athlete {athlete_id}, lift {lift.value}. "
                "Use overwrite=True to replace."
            )
        
        init_result = initialize_lift_capacity(
            lift=lift,
            input_type=CapacityInputType(input_type),
            input_load_kg=input_load_kg,
            input_reps=input_reps,
            input_rpe=input_rpe
        )
        
        if existing:
            existing.input_type = input_type
            existing.input_load_kg = input_load_kg
            existing.input_reps = input_reps
            existing.input_rpe = input_rpe
            existing.anchor_capacity = init_result.anchor_capacity
            existing.model_capacity = init_result.model_capacity
            existing.confidence = init_result.confidence.value
            existing.provisional_breakthrough_count = 0
            existing.last_provisional_at = None
            existing.last_signal_value = None
            profile = existing
        else:
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
        velocity_loss: Optional[float] = None,
        observed_velocity: Optional[float] = None,
    ) -> Dict:
        """
        Process a strength set for capacity estimation.
        
        Evaluates set quality and detects breakthroughs using refined logic.
        """
        profile = self.get_or_create_profile(athlete_id, lift)
        
        # Check if this is a quality set (lift-specific criteria)
        quality_result = is_quality_strength_set(
            lift=lift,
            load_kg=load_kg,
            reps=reps,
            rpe=rpe,
            velocity_loss=velocity_loss,
            observed_velocity=observed_velocity,
            anchor_capacity=profile.anchor_capacity
        )
        
        if not quality_result.is_quality:
            return {
                "is_quality": False,
                "reason": quality_result.reason,
                "breakthrough": None
            }
        
        signal = quality_result.signal
        profile.last_signal_value = signal.signal_value
        
        # Parse last_provisional_at
        last_provisional_at = profile.last_provisional_at
        
        # Detect breakthrough with refined logic
        confidence = CapacityConfidence(profile.confidence)
        breakthrough = detect_breakthrough_v2(
            anchor_capacity=profile.anchor_capacity,
            model_capacity=profile.model_capacity,
            signal=signal,
            confidence=confidence,
            provisional_count=profile.provisional_breakthrough_count,
            last_provisional_at=last_provisional_at
        )
        
        result = {
            "is_quality": True,
            "signal_type": signal.signal_type.value,
            "signal_value": signal.signal_value,
            "quality_score": signal.quality_score,
            "breakthrough": {
                "is_provisional": breakthrough.is_provisional_breakthrough,
                "is_confirmed": breakthrough.is_confirmed_breakthrough,
                "signal_delta_pct": breakthrough.signal_delta_pct,
                "reason": breakthrough.reason
            }
        }
        
        # Update profile based on breakthrough result
        if breakthrough.is_confirmed_breakthrough:
            # Confirmed: partial anchor update
            profile.anchor_capacity = breakthrough.new_anchor_capacity
            profile.model_capacity = breakthrough.new_model_capacity
            profile.provisional_breakthrough_count = 0
            profile.last_confirmed_breakthrough_at = datetime.utcnow()
            profile.last_provisional_at = None
            profile.confidence = CapacityConfidence.HIGH.value
            result["breakthrough"]["new_anchor"] = breakthrough.new_anchor_capacity
            result["breakthrough"]["previous_anchor"] = profile.anchor_capacity - (breakthrough.new_anchor_capacity - profile.anchor_capacity) * 2
            
        elif breakthrough.is_provisional_breakthrough:
            # Provisional: increment count, update model only
            profile.provisional_breakthrough_count += 1
            profile.model_capacity = breakthrough.new_model_capacity
            profile.last_provisional_at = datetime.utcnow()
            result["breakthrough"]["provisional_count"] = profile.provisional_breakthrough_count
            
        else:
            # No breakthrough: model may drift slightly
            if breakthrough.new_model_capacity is not None:
                profile.model_capacity = breakthrough.new_model_capacity
            
            # Reset provisional count if signal is significantly below anchor
            if breakthrough.signal_delta_pct < -5:
                profile.provisional_breakthrough_count = 0
                profile.last_provisional_at = None
        
        self.db.commit()
        self.db.refresh(profile)
        
        return result
    
    def get_model_capacity(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> float:
        """Get current model capacity for a lift (operational estimate)."""
        profile = self.get_or_create_profile(athlete_id, lift)
        return profile.model_capacity
    
    def get_anchor_capacity(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> float:
        """Get current anchor capacity for a lift (stable reference)."""
        profile = self.get_or_create_profile(athlete_id, lift)
        return profile.anchor_capacity
    
    def confirm_provisional_breakthrough(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> Optional[Dict]:
        """Manually confirm a provisional breakthrough."""
        profile = self.get_profile(athlete_id, lift)
        
        if not profile or profile.provisional_breakthrough_count == 0:
            return None
        
        if profile.last_signal_value is None:
            return None
        
        # Manual confirmation: apply partial update
        previous_anchor = profile.anchor_capacity
        new_anchor = apply_confirmed_breakthrough(
            current_anchor=profile.anchor_capacity,
            signal_value=profile.last_signal_value
        )
        new_model = update_model_capacity(new_anchor, profile.last_signal_value)
        
        profile.anchor_capacity = new_anchor
        profile.model_capacity = new_model
        profile.provisional_breakthrough_count = 0
        profile.last_confirmed_breakthrough_at = datetime.utcnow()
        profile.last_provisional_at = None
        profile.confidence = CapacityConfidence.HIGH.value
        
        self.db.commit()
        self.db.refresh(profile)
        
        improvement_pct = (new_anchor - previous_anchor) / previous_anchor * 100
        
        return {
            "confirmed": True,
            "new_anchor": new_anchor,
            "previous_anchor": previous_anchor,
            "improvement_pct": improvement_pct
        }
    
    def reset_provisional_breakthroughs(
        self,
        athlete_id: int,
        lift: LiftType
    ) -> bool:
        """Reset provisional breakthrough count."""
        profile = self.get_profile(athlete_id, lift)
        
        if not profile:
            return False
        
        profile.provisional_breakthrough_count = 0
        profile.last_provisional_at = None
        
        self.db.commit()
        return True
    
    def recompute_capacity_from_history(
        self,
        athlete_id: int,
        lift: LiftType,
        days_back: int = 90
    ) -> Dict:
        """
        Recompute capacity by scanning recent sessions.
        
        Optional endpoint for batch processing historical data.
        """
        from datetime import date, timedelta
        from app.services.engine_orchestrator import EngineOrchestrator
        
        profile = self.get_or_create_profile(athlete_id, lift)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        
        orchestrator = EngineOrchestrator(self.db)
        sessions = orchestrator.get_recent_sessions(athlete_id, start_date, end_date)
        
        # Filter to target lift
        lift_sessions = [
            s for s in sessions.get("strength", [])
            if s.lift == lift
        ]
        
        signals_processed = 0
        breakthroughs_detected = 0
        
        for session in lift_sessions:
            if not session.raw_data:
                continue
            
            sets_data = session.raw_data.get("sets", [])
            for set_data in sets_data:
                result = self.process_quality_set(
                    athlete_id=athlete_id,
                    lift=lift,
                    load_kg=set_data.get("load", 0),
                    reps=set_data.get("reps", 0),
                    rpe=set_data.get("rpe"),
                    velocity_loss=set_data.get("velocity_loss"),
                    observed_velocity=set_data.get("observed_velocity"),
                )
                
                if result["is_quality"]:
                    signals_processed += 1
                    if result["breakthrough"]["is_provisional"] or result["breakthrough"]["is_confirmed"]:
                        breakthroughs_detected += 1
        
        self.db.refresh(profile)
        
        return {
            "athlete_id": athlete_id,
            "lift": lift.value,
            "sessions_scanned": len(lift_sessions),
            "signals_processed": signals_processed,
            "breakthroughs_detected": breakthroughs_detected,
            "current_anchor": profile.anchor_capacity,
            "current_model": profile.model_capacity,
            "confidence": profile.confidence
        }
