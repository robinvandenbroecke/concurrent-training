"""
EngineOrchestrator - Single Source of Truth for Concurrent Training

Sprint A: CONSOLIDATION
- Replaces legacy ConcurrentTrainingModel pipeline with modular engines
- Coordinates: rep_engine -> day_engine -> performance_engine
- All production ingestion flows through this orchestrator
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import os
import json
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app import models as db_models
from app.types import LiftType, EnduranceSport

# Domain engines
from app.domain.rep_engine import (
    LiftVelocityProfile,
    RepEngineParams,
    SetInput,
    SessionInput,
    simulate_strength_session,
)

# Sprint E2.1: Capacity lookup for production strength impulse path
from app.services.capacity_service import get_lift_capacity_estimate, normalize_lift_type
from app.services.strength_impulse_features import compute_strength_impulse_features
from app.domain.day_engine import (
    DayEngineParams,
    SetImpulse,
    StrengthImpulses,
    EnduranceImpulses,
    DailyImpulses,
    PerLiftState,
    DayState,
    update_day_state,
    compute_readiness,
    ReadinessOutput as Readiness,
)

# Use canonical EnduranceSport (EnduranceMode is deprecated alias)
EnduranceMode = EnduranceSport
from app.domain.performance_engine import (
    StrengthSessionMetrics,
    EnduranceSessionMetrics,
    analyze_lift_trend,
    compute_session_e1rm,
)


# Feature flag for legacy model
USE_LEGACY_MODEL = os.getenv("USE_LEGACY_MODEL", "false").lower() == "true"


class EngineOrchestrator:
    """
    Orchestrates all domain engines for session ingestion and state updates.
    
    This is the SINGLE SOURCE OF TRUTH for:
    - Strength session ingestion (uses rep_engine)
    - Endurance session ingestion
    - Day state updates (uses day_engine)
    - Performance snapshots (uses performance_engine)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.rep_params = RepEngineParams()
        self.day_params = DayEngineParams()

    # -------------------------------------------------------------------------
    # HOTFIX: Idempotency - Content hash computation
    # -------------------------------------------------------------------------

    def _compute_strength_content_hash(
        self,
        athlete_id: int,
        session_date: date,
        lift: str,
        sets_data: List[Dict[str, Any]],
        optional_rpe: Optional[float] = None
    ) -> str:
        """
        Compute deterministic content hash for strength session.
        Used for idempotency - prevents double-counting sessions.
        """
        # Build canonical representation
        canonical_sets = []
        for set_data in sorted(sets_data, key=lambda x: (x.get("load_kg", 0), x.get("reps", 0))):
            velocities = set_data.get("velocities", [])
            # Round velocities to 3 decimals for stability
            rounded_velocities = [round(v, 3) for v in velocities]

            canonical_sets.append({
                "lift": lift,
                "load_kg": round(set_data.get("load_kg", 0), 2),
                "reps": set_data.get("reps", 0),
                "velocities": rounded_velocities,
                "rest_sec": round(set_data.get("rest_sec", 0), 1) if set_data.get("rest_sec") else None,
            })

        canonical = {
            "athlete_id": athlete_id,
            "date": session_date.isoformat(),
            "sets": canonical_sets,
            "rpe": round(optional_rpe, 1) if optional_rpe else None,
        }

        # Deterministic JSON (sorted keys, no whitespace)
        json_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    def _compute_endurance_content_hash(
        self,
        athlete_id: int,
        session_date: date,
        sport: str,
        duration_minutes: float,
        intensity_type: str,
        power_data: Optional[List[Dict]] = None
    ) -> str:
        """
        Compute deterministic content hash for endurance session.
        Used for idempotency - prevents double-counting sessions.
        """
        # Build canonical representation
        canonical_power = None
        if power_data:
            # Round power values to 1 decimal for stability
            canonical_power = [
                {"power": round(p.get("power", 0), 1), "timestamp": p.get("timestamp")}
                for p in sorted(power_data, key=lambda x: x.get("timestamp", 0))
            ]

        canonical = {
            "athlete_id": athlete_id,
            "date": session_date.isoformat(),
            "sport": sport,
            "duration_minutes": round(duration_minutes, 1),
            "intensity_type": intensity_type,
            "power_data": canonical_power,
        }

        # Deterministic JSON (sorted keys, no whitespace)
        json_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    def _check_existing_strength_session(
        self,
        athlete_id: int,
        content_hash: str
    ) -> Optional[db_models.StrengthSession]:
        """Check if strength session with this hash already exists."""
        if not content_hash:
            return None
        return self.db.query(db_models.StrengthSession).filter(
            db_models.StrengthSession.athlete_id == athlete_id,
            db_models.StrengthSession.content_hash == content_hash
        ).first()

    def _check_existing_endurance_session(
        self,
        athlete_id: int,
        content_hash: str
    ) -> Optional[db_models.EnduranceSession]:
        """Check if endurance session with this hash already exists."""
        if not content_hash:
            return None
        return self.db.query(db_models.EnduranceSession).filter(
            db_models.EnduranceSession.athlete_id == athlete_id,
            db_models.EnduranceSession.content_hash == content_hash
        ).first()
    
    def ingest_strength_session(
        self,
        athlete_id: int,
        lift: LiftType,
        session_date: date,
        sets_data: List[Dict[str, Any]],
        vbt_available: bool = True,
        optional_rpe: Optional[float] = None,
    ) -> Tuple[db_models.StrengthSession, DayState, Dict]:
        """
        Ingest a strength session using rep_engine and update day state.
        
        Args:
            athlete_id: Athlete ID
            lift: Lift type
            session_date: Date of session
            sets_data: List of set data with velocities
                     Format: [{"load_kg": float, "reps": int, "velocities": [float], "rest_sec": float}]
            vbt_available: Whether VBT data is available
            optional_rpe: Optional session RPE for central/local split
        
        Returns:
            (strength_session_db, updated_day_state, performance_snapshot)
        """
        # Get athlete's lift profile
        profile_db = self.db.query(db_models.LiftProfile).filter(
            db_models.LiftProfile.athlete_id == athlete_id,
            db_models.LiftProfile.lift == lift
        ).first()
        
        if not profile_db:
            raise ValueError(f"No profile found for {lift}")

        # HOTFIX: Check idempotency - compute content hash before processing
        content_hash = self._compute_strength_content_hash(
            athlete_id, session_date, lift.value, sets_data, optional_rpe
        )

        # Check if session already exists
        existing_session = self._check_existing_strength_session(athlete_id, content_hash)
        if existing_session:
            # Return existing session without double-applying impulses
            existing_day_state = self._get_or_create_day_state(athlete_id, session_date, create=False)
            if existing_day_state is None:
                existing_day_state = self._get_or_create_day_state(athlete_id, session_date)
            # Return empty performance snapshot for idempotent case
            return existing_session, existing_day_state, {"idempotent": True, "existing_session_id": existing_session.id}

        # Convert to rep_engine profile with validation/sanitization
        a_val = profile_db.a
        b_val = profile_db.b
        
        # Fix invalid profile values
        if b_val <= 0:
            # b must be positive so v_ref decreases with load
            b_val = abs(b_val) if b_val != 0 else 0.003
        if a_val <= 0:
            a_val = 0.55  # Default intercept
        
        try:
            profile = LiftVelocityProfile(
                lift=lift.value,
                a=a_val,
                b=b_val
            )
        except ValueError as e:
            # Fall back to calibrated profile if validation fails
            profile = LiftVelocityProfile.calibrated_profile(lift.value)
            # Update DB with corrected values
            profile_db.a = profile.a
            profile_db.b = profile.b
            self.db.commit()

        # Get current day state
        day_state = self._get_or_create_day_state(athlete_id, session_date)
        
        # Convert sets_data to rep_engine SetInput
        set_inputs = []
        total_tonnage = 0
        total_reps = 0
        
        for i, set_data in enumerate(sets_data):
            load_kg = set_data.get("load_kg", 0)
            reps = set_data.get("reps", 0)
            velocities = set_data.get("velocities", [])
            rest_sec = set_data.get("rest_sec")
            
            total_tonnage += load_kg * reps
            total_reps += reps
            
            set_inputs.append(SetInput(
                lift=lift.value,
                load_kg=load_kg,
                velocities=velocities,
                rest_before_sec=rest_sec if i > 0 else None
            ))
        
        # Build rep_engine session input
        # Map current day state to rep_engine initial conditions
        init_A_local = {
            lift.value: max(0.1, 1.0 - day_state.per_lift.get(lift.value, PerLiftState()).D_l / 2)
        }
        init_A_sys = max(0.1, 1.0 - day_state.D_sys / 2)
        init_M = 0.0  # Start fresh for session
        
        session_input = SessionInput(
            sets=set_inputs,
            profiles={lift.value: profile},
            init_A_local=init_A_local,
            init_A_sys=init_A_sys,
            init_M=init_M,
            R_mito=day_state.R_mito,
            params=self.rep_params
        )
        
        # Run rep_engine simulation
        rep_output = simulate_strength_session(session_input)
        
        # v9.1: CONCURRENCY-SAFE idempotency - try insert, catch IntegrityError
        strength_session = db_models.StrengthSession(
            athlete_id=athlete_id,
            lift=lift,
            start_time=datetime.combine(session_date, datetime.min.time()),
            content_hash=content_hash,
            tonnage=total_tonnage,
            avg_intensity=total_tonnage / max(total_reps, 1) if total_reps > 0 else 0,
            raw_data={
                "sets": sets_data,
                "final_A_local": rep_output.final_A_local,
                "final_A_sys": rep_output.final_A_sys,
                "final_A_M": rep_output.final_A_M,
            },
            rep_level_log=[
                {
                    "set_idx": s_idx,
                    "rep_idx": r_idx,
                    "A_l": rep.A_l,
                    "A_sys": rep.A_sys,
                    "A_M": rep.A_M,
                    "v_pred_next": rep.v_pred_next,
                }
                for s_idx, set_out in enumerate(rep_output.sets)
                for r_idx, rep in enumerate(set_out.reps)
            ]
        )
        self.db.add(strength_session)
        
        try:
            self.db.flush()  # Get ID without committing
        except IntegrityError:
            # v9.1: Concurrent duplicate - rollback and return existing
            self.db.rollback()
            existing_session = self._check_existing_strength_session(athlete_id, content_hash)
            if existing_session:
                existing_day_state = self._get_or_create_day_state(athlete_id, session_date, create=False)
                if existing_day_state is None:
                    existing_day_state = self._get_or_create_day_state(athlete_id, session_date)
                return existing_session, existing_day_state, {"idempotent": True, "concurrent": True, "existing_session_id": existing_session.id}
            # Should not reach here, but re-raise if we do
            raise
        
        # Compute strength impulses for day_engine
        strength_impulses = self._compute_strength_impulses(
            lift.value, sets_data, rep_output,
            athlete_id=athlete_id,
            session_date=session_date,
        )
        
        # Update day state
        daily_impulses = DailyImpulses(
            strength=strength_impulses,
            endurance=EnduranceImpulses(
                u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0,
                mode=EnduranceMode.CYCLING, has_HIIT=False, has_Z2=False
            ),
            date=session_date
        )
        
        updated_day_state = update_day_state(day_state, daily_impulses, self.day_params)
        
        # Persist updated day state
        self._persist_day_state(athlete_id, session_date, updated_day_state)
        
        # Compute performance snapshot
        performance_snapshot = self._compute_strength_performance_snapshot(
            athlete_id, lift, session_date, sets_data, rep_output, vbt_available
        )
        
        self.db.commit()
        
        return strength_session, updated_day_state, performance_snapshot
    
    def ingest_endurance_session(
        self,
        athlete_id: int,
        session_date: date,
        sport: EnduranceSport,
        duration_minutes: float,
        intensity_type: str,  # "z2", "hiit", "mixed"
        power_data: Optional[List[Dict]] = None,
    ) -> Tuple[db_models.EnduranceSession, DayState, Dict]:
        """
        Ingest an endurance session and update day state.
        
        Args:
            athlete_id: Athlete ID
            session_date: Date of session
            sport: Endurance sport type
            duration_minutes: Session duration
            intensity_type: "z2", "hiit", or "mixed"
            power_data: Optional power meter data
        
        Returns:
            (endurance_session_db, updated_day_state, performance_snapshot)
        """
        # HOTFIX: Check idempotency - compute content hash before processing
        content_hash = self._compute_endurance_content_hash(
            athlete_id, session_date, sport.value, duration_minutes, intensity_type, power_data
        )

        # Check if session already exists
        existing_session = self._check_existing_endurance_session(athlete_id, content_hash)
        if existing_session:
            # Return existing session without double-applying impulses
            existing_day_state = self._get_or_create_day_state(athlete_id, session_date, create=False)
            if existing_day_state is None:
                existing_day_state = self._get_or_create_day_state(athlete_id, session_date)
            # Return empty performance snapshot for idempotent case
            return existing_session, existing_day_state, {"idempotent": True, "existing_session_id": existing_session.id}

        # Get current day state
        day_state = self._get_or_create_day_state(athlete_id, session_date)

        # Compute endurance impulses
        u_E_Z2, u_E_HIIT = self._compute_endurance_impulses(
            duration_minutes, intensity_type, power_data
        )
        
        # Map sport to endurance mode
        mode_map = {
            EnduranceSport.RUNNING: EnduranceMode.RUNNING,
            EnduranceSport.CYCLING: EnduranceMode.CYCLING,
            EnduranceSport.SWIMMING: EnduranceMode.SWIMMING,
        }
        mode = mode_map.get(sport, EnduranceMode.CYCLING)
        
        endurance_impulses = EnduranceImpulses(
            u_E_Z2=u_E_Z2,
            u_E_HIIT=u_E_HIIT,
            u_E_total=u_E_Z2 + u_E_HIIT,
            mode=mode,
            has_HIIT=intensity_type in ["hiit", "mixed"],
            has_Z2=intensity_type in ["z2", "mixed"]
        )
        
        # Update day state
        daily_impulses = DailyImpulses(
            strength=StrengthImpulses(
                per_lift={}, u_sys=0.0, u_legs=0.0, u_met=0.0,
                u_legs_high_intensity=0.0, sets=[]
            ),
            endurance=endurance_impulses,
            date=session_date
        )
        
        updated_day_state = update_day_state(day_state, daily_impulses, self.day_params)
        
        # v9.1: CONCURRENCY-SAFE idempotency - try insert, catch IntegrityError
        endurance_session = db_models.EnduranceSession(
            athlete_id=athlete_id,
            sport=sport,
            start_time=datetime.combine(session_date, datetime.min.time()),
            content_hash=content_hash,
            duration_minutes=duration_minutes,
            intensity_type=intensity_type,
            u_E_Z2=u_E_Z2,
            u_E_HIIT=u_E_HIIT,
            raw_data={
                "power_data": power_data,
                "impulses": {"u_E_Z2": u_E_Z2, "u_E_HIIT": u_E_HIIT}
            }
        )
        self.db.add(endurance_session)

        try:
            self.db.flush()
        except IntegrityError:
            # v9.1: Concurrent duplicate - rollback and return existing
            self.db.rollback()
            existing_session = self._check_existing_endurance_session(athlete_id, content_hash)
            if existing_session:
                existing_day_state = self._get_or_create_day_state(athlete_id, session_date, create=False)
                if existing_day_state is None:
                    existing_day_state = self._get_or_create_day_state(athlete_id, session_date)
                return existing_session, existing_day_state, {"idempotent": True, "concurrent": True, "existing_session_id": existing_session.id}
            raise

        # Persist updated day state
        self._persist_day_state(athlete_id, session_date, updated_day_state)
        
        # Compute performance snapshot
        performance_snapshot = self._compute_endurance_performance_snapshot(
            athlete_id, sport, session_date, duration_minutes, intensity_type, power_data
        )
        
        self.db.commit()
        
        return endurance_session, updated_day_state, performance_snapshot
    
    def get_day_state_snapshot(
        self,
        athlete_id: int,
        query_date: date
    ) -> Optional[DayState]:
        """
        Get day state snapshot for athlete on specific date.
        Used by coach, program, and performance engines.
        """
        return self._get_or_create_day_state(athlete_id, query_date, create=False)
    
    def get_day_state_with_carryover(
        self,
        athlete_id: int,
        query_date: date
    ) -> Optional[DayState]:
        """
        Get day state with guaranteed carryover from prior days.
        
        Unlike get_day_state_snapshot, this method ALWAYS computes the state
        by decaying forward from the most recent prior day state, ensuring
        continuity even if the target date has sessions stored with incomplete
        carryover data.
        
        Used by replay and validation to show correct day-to-day state evolution.
        """
        date_str = query_date.isoformat()
        
        # Find most recent prior day state
        prior_state_db = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date < date_str
        ).order_by(db_models.DayState.date.desc()).first()
        
        if prior_state_db:
            # Load the prior state
            prior_date = date.fromisoformat(prior_state_db.date)
            prior_lift_states = self.db.query(db_models.LiftDayState).filter(
                db_models.LiftDayState.athlete_id == athlete_id,
                db_models.LiftDayState.date == prior_state_db.date
            ).all()
            
            per_lift = {}
            for ls in prior_lift_states:
                per_lift[ls.lift.value] = PerLiftState(
                    D_l=ls.D_l,
                    F_l=ls.F_l,
                    C_l=ls.C_l
                )
            
            prior_day_state = DayState(
                date=prior_date,
                per_lift=per_lift,
                D_sys=prior_state_db.D_sys,
                R_mito=prior_state_db.R_mito,
                E_fat=prior_state_db.E_fat,
                T_legs=getattr(prior_state_db, 'T_legs', 0.0)
            )
            
            # Decay to target date
            from app.domain.day_engine import decay_day_state_to_date
            return decay_day_state_to_date(prior_day_state, query_date, self.day_params)
        
        # No prior state - check if target date has a state
        return self._get_or_create_day_state(athlete_id, query_date, create=False)
    
    def get_recent_sessions(
        self,
        athlete_id: int,
        date_from: date,
        date_to: date
    ) -> Dict[str, List]:
        """
        Get recent sessions for performance analysis.
        
        Returns:
            {"strength": [...], "endurance": [...]}
        """
        strength_sessions = self.db.query(db_models.StrengthSession).filter(
            db_models.StrengthSession.athlete_id == athlete_id,
            db_models.StrengthSession.start_time >= datetime.combine(date_from, datetime.min.time()),
            db_models.StrengthSession.start_time <= datetime.combine(date_to, datetime.max.time())
        ).all()
        
        endurance_sessions = self.db.query(db_models.EnduranceSession).filter(
            db_models.EnduranceSession.athlete_id == athlete_id,
            db_models.EnduranceSession.start_time >= datetime.combine(date_from, datetime.min.time()),
            db_models.EnduranceSession.start_time <= datetime.combine(date_to, datetime.max.time())
        ).all()
        
        return {
            "strength": strength_sessions,
            "endurance": endurance_sessions
        }
    
    def compute_readiness(
        self,
        athlete_id: int,
        query_date: date
    ) -> Readiness:
        """Compute readiness for athlete on specific date."""
        day_state = self._get_or_create_day_state(athlete_id, query_date)
        return compute_readiness(day_state, self.day_params)
    
    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    
    def _get_or_create_day_state(
        self,
        athlete_id: int,
        query_date: date,
        create: bool = True
    ) -> DayState:
        """Get or create day state for athlete on date."""
        date_str = query_date.isoformat()
        
        # Try to load from DB
        day_state_db = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == date_str
        ).first()
        
        lift_states_db = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.date == date_str
        ).all()
        
        if day_state_db and lift_states_db:
            # Convert DB models to domain DayState
            per_lift = {}
            for ls in lift_states_db:
                per_lift[ls.lift.value] = PerLiftState(
                    D_l=ls.D_l,
                    F_l=ls.F_l,
                    C_l=ls.C_l
                )
            
            return DayState(
                date=query_date,
                per_lift=per_lift,
                D_sys=day_state_db.D_sys,
                R_mito=day_state_db.R_mito,
                E_fat=day_state_db.E_fat,
                T_legs=getattr(day_state_db, 'T_legs', 0.0)
            )
        
        if not create:
            return None
        
        # v9.2: Look for most recent prior day state and decay it forward
        prior_state_db = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date < date_str
        ).order_by(db_models.DayState.date.desc()).first()
        
        if prior_state_db:
            # Load the prior state
            prior_date = date.fromisoformat(prior_state_db.date)
            prior_lift_states = self.db.query(db_models.LiftDayState).filter(
                db_models.LiftDayState.athlete_id == athlete_id,
                db_models.LiftDayState.date == prior_state_db.date
            ).all()
            
            per_lift = {}
            for ls in prior_lift_states:
                per_lift[ls.lift.value] = PerLiftState(
                    D_l=ls.D_l,
                    F_l=ls.F_l,
                    C_l=ls.C_l
                )
            
            prior_day_state = DayState(
                date=prior_date,
                per_lift=per_lift,
                D_sys=prior_state_db.D_sys,
                R_mito=prior_state_db.R_mito,
                E_fat=prior_state_db.E_fat,
                T_legs=getattr(prior_state_db, 'T_legs', 0.0)
            )
            
            # Decay to target date
            from app.domain.day_engine import decay_day_state_to_date
            decayed_state = decay_day_state_to_date(prior_day_state, query_date, self.day_params)
            return decayed_state
        
        if not create:
            return None
        
        # No prior state - create fresh default
        per_lift = {}
        for lt in LiftType:
            per_lift[lt.value] = PerLiftState(D_l=0.0, F_l=1.0, C_l=100.0)
        
        return DayState(
            date=query_date,
            per_lift=per_lift,
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0,
            T_legs=0.0
        )
    
    def _persist_day_state(
        self,
        athlete_id: int,
        query_date: date,
        day_state: DayState
    ) -> None:
        """Persist day state to DB."""
        date_str = query_date.isoformat()
        
        # Update or create system day state
        day_state_db = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == date_str
        ).first()
        
        # HOTFIX: Persist T_legs along with other day state fields
        if day_state_db:
            day_state_db.D_sys = day_state.D_sys
            day_state_db.R_mito = day_state.R_mito
            day_state_db.E_fat = day_state.E_fat
            day_state_db.T_legs = getattr(day_state, 'T_legs', 0.0)
        else:
            day_state_db = db_models.DayState(
                athlete_id=athlete_id,
                date=date_str,
                D_sys=day_state.D_sys,
                R_mito=day_state.R_mito,
                E_fat=day_state.E_fat,
                T_legs=getattr(day_state, 'T_legs', 0.0)
            )
            self.db.add(day_state_db)
        
        # Update per-lift states
        for lift_name, lift_state in day_state.per_lift.items():
            lift_enum = LiftType(lift_name)
            
            lift_day_state = self.db.query(db_models.LiftDayState).filter(
                db_models.LiftDayState.athlete_id == athlete_id,
                db_models.LiftDayState.lift == lift_enum,
                db_models.LiftDayState.date == date_str
            ).first()
            
            if lift_day_state:
                lift_day_state.D_l = lift_state.D_l
                lift_day_state.F_l = lift_state.F_l
                lift_day_state.C_l = lift_state.C_l
            else:
                lift_day_state = db_models.LiftDayState(
                    athlete_id=athlete_id,
                    lift=lift_enum,
                    date=date_str,
                    D_l=lift_state.D_l,
                    F_l=lift_state.F_l,
                    C_l=lift_state.C_l
                )
                self.db.add(lift_day_state)
    
    def _compute_strength_impulses(
        self,
        lift: str,
        sets_data: List[Dict],
        rep_output: Any,
        athlete_id: Optional[int] = None,
        session_date: Optional[date] = None,
    ) -> StrengthImpulses:
        """Compute strength impulses from rep_engine output.

        Sprint E2.2: Uses athlete/lift-specific capacity lookup with full hierarchy.
        NEVER falls back to universal 200kg - always uses lift-specific default.

        Sprint P1: Uses real rep_engine-derived velocity_factor and vl.
        Replaces placeholder values (0.9, 0.15) with actual y and VL from rep_output.
        """
        per_lift = {lift: 0.0}
        u_sys = 0.0
        u_legs = 0.0
        u_met = 0.0
        u_legs_high_intensity = 0.0
        set_impulses = []
        
        # Check if this is a legs lift
        is_legs = lift in ['squat', 'deadlift', 'clean']
        
        # Sprint E2.2: Get athlete/lift-specific capacity estimate via canonical lookup
        # No fallback default here - let the lookup handle it properly
        capacity_estimate, capacity_source = get_lift_capacity_estimate(
            db=self.db,
            athlete_id=athlete_id,
            lift=lift,
            query_date=session_date,
        )
        
        for set_idx, set_data in enumerate(sets_data):
            load_kg = set_data.get("load_kg", 0)
            reps = set_data.get("reps", 0)

            # Sprint E2.1: Use capacity-based intensity with clamping
            # intensity = load / capacity, clamped to [0.20, 1.20]
            intensity = load_kg / max(capacity_estimate, 1.0)
            intensity = max(0.20, min(1.20, intensity))

            impulse = (load_kg * reps) * (intensity ** 1.2)

            per_lift[lift] += impulse
            u_sys += impulse * (1.3 if is_legs else 0.7)

            if is_legs:
                u_legs += impulse
                if intensity > 0.85:
                    u_legs_high_intensity += impulse * 0.5

            # Sprint P1: Compute real velocity_factor and vl from rep_engine output
            features = compute_strength_impulse_features(
                rep_output=rep_output,
                set_idx=set_idx,
                set_data=set_data,
                lift=lift,
            )

            set_impulses.append(SetImpulse(
                lift=lift,
                tonnage=load_kg * reps,
                intensity=intensity,
                velocity_factor=features.velocity_factor,
                vl=features.vl if features.vl is not None else 0.0,
                reps=reps,
                avg_intensity_pct=intensity * 100
            ))
        
        # Sprint P1: Collect per-set features for debug summary
        feature_sources = [s.velocity_factor for s in set_impulses]
        vl_values = [s.vl for s in set_impulses]

        # Store capacity info in internal summary for debugging
        impulses = StrengthImpulses(
            per_lift=per_lift,
            u_sys=u_sys,
            u_legs=u_legs,
            u_met=u_met,
            u_legs_high_intensity=u_legs_high_intensity,
            sets=set_impulses
        )

        # Sprint P1: Attach debug metadata (non-breaking)
        impulses._capacity_estimate = capacity_estimate
        impulses._capacity_source = capacity_source
        impulses._velocity_factors = feature_sources
        impulses._vl_values = vl_values

        return impulses
    
    def _compute_endurance_impulses(
        self,
        duration_minutes: float,
        intensity_type: str,
        power_data: Optional[List[Dict]]
    ) -> Tuple[float, float]:
        """Compute endurance impulses (u_E_Z2, u_E_HIIT)."""
        # Match legacy behavior for backward compatibility
        if intensity_type == "z2":
            return duration_minutes, 0.0
        elif intensity_type == "hiit":
            return 0.0, duration_minutes
        elif intensity_type == "mixed":
            return duration_minutes * 0.3, duration_minutes * 0.7
        else:
            return duration_minutes * 0.5, 0.0
    
    def _compute_strength_performance_snapshot(
        self,
        athlete_id: int,
        lift: LiftType,
        session_date: date,
        sets_data: List[Dict],
        rep_output: Any,
        vbt_available: bool
    ) -> Dict:
        """Compute performance snapshot for strength session."""
        # Build sets_data for e1RM calculation
        e1rm_sets = []
        for set_data in sets_data:
            load_kg = set_data.get("load_kg", 0)
            reps = set_data.get("reps", 0)
            velocities = set_data.get("velocities", [])
            
            # Estimate velocity loss if we have velocities
            vl = 0.0
            if len(velocities) >= 2:
                vl = (velocities[0] - velocities[-1]) / max(velocities[0], 0.001)
            
            e1rm_sets.append({
                "load": load_kg,
                "reps": reps,
                "velocity_loss": vl
            })
        
        e1rm_est, top_load, top_reps, top_vl, method = compute_session_e1rm(
            e1rm_sets, vbt_available=vbt_available
        )
        
        snapshot = {
            "athlete_id": athlete_id,
            "date": session_date.isoformat(),
            "lift": lift.value,
            "e1rm_est": e1rm_est,
            "top_load": top_load,
            "top_reps": top_reps,
            "method": method,
            "final_A_local": rep_output.final_A_local,
            "final_A_sys": rep_output.final_A_sys,
            "final_A_M": rep_output.final_A_M,
        }
        
        # Store in performance_snapshots table if it exists
        self._store_performance_snapshot(athlete_id, session_date, "strength", lift.value, snapshot)
        
        return snapshot
    
    def _compute_endurance_performance_snapshot(
        self,
        athlete_id: int,
        sport: EnduranceSport,
        session_date: date,
        duration_minutes: float,
        intensity_type: str,
        power_data: Optional[List[Dict]]
    ) -> Dict:
        """Compute performance snapshot for endurance session."""
        snapshot = {
            "athlete_id": athlete_id,
            "date": session_date.isoformat(),
            "sport": sport.value,
            "duration_minutes": duration_minutes,
            "intensity_type": intensity_type,
        }
        
        if power_data:
            # Compute normalized power, TSS, etc.
            avg_power = sum(p.get("power", 0) for p in power_data) / len(power_data)
            snapshot["avg_power"] = avg_power
        
        self._store_performance_snapshot(athlete_id, session_date, "endurance", sport.value, snapshot)
        
        return snapshot
    
    def _store_performance_snapshot(
        self,
        athlete_id: int,
        session_date: date,
        session_type: str,
        subtype: str,
        data: Dict
    ) -> None:
        """Store performance snapshot if table exists."""
        # Check if PerformanceSnapshot model exists with expected fields
        if hasattr(db_models, 'PerformanceSnapshot'):
            # Check if snapshot already exists for this date
            existing = self.db.query(db_models.PerformanceSnapshot).filter(
                db_models.PerformanceSnapshot.athlete_id == athlete_id,
                db_models.PerformanceSnapshot.snapshot_date == session_date.isoformat()
            ).first()
            
            if existing:
                # Update existing snapshot
                existing.metrics_json = {
                    "session_type": session_type,
                    "subtype": subtype,
                    "data": data
                }
            else:
                snapshot = db_models.PerformanceSnapshot(
                    athlete_id=athlete_id,
                    snapshot_date=session_date.isoformat(),
                    days_analyzed=1,
                    metrics_json={
                        "session_type": session_type,
                        "subtype": subtype,
                        "data": data
                    },
                    overall_signal="maintain"
                )
                self.db.add(snapshot)
