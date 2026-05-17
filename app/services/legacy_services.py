"""
Services layer - connects domain model to persistence

SPRINT A: CONSOLIDATION - Single Source of Truth
- SessionService now uses EngineOrchestrator by default (modular engines)
- Legacy ConcurrentTrainingModel available via USE_LEGACY_MODEL env flag
"""
import os
from datetime import datetime, date, time as dt_time
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.types import LiftType, EnduranceSport
from app.domain.legacy_model import (
    ConcurrentTrainingModel, Autoregulator,
    DayLevelState, RepLevelState, SystemParameters as DomainParams
)
from app import models as db_models
from app import schemas

# Sprint A: Import new orchestrator
from app.services.engine_orchestrator import EngineOrchestrator, USE_LEGACY_MODEL


class AthleteService:
    """Athlete management"""
    
    @staticmethod
    def create_athlete(db: Session, name: str) -> db_models.Athlete:
        athlete = db_models.Athlete(name=name)
        db.add(athlete)
        db.commit()
        db.refresh(athlete)
        
        # Create default lift profiles
        default_profiles = {
            LiftType.SQUAT: {"a": 0.55, "b": 0.0032},
            LiftType.BENCH: {"a": 0.60, "b": 0.0028},
            LiftType.DEADLIFT: {"a": 0.50, "b": 0.0030},
            LiftType.PRESS: {"a": 0.58, "b": 0.0025},
            LiftType.POWER_CLEAN: {"a": 0.75, "b": 0.0040},
        }
        
        for lift, params in default_profiles.items():
            profile = db_models.LiftProfile(
                athlete_id=athlete.id,
                lift=lift,
                a=params["a"],
                b=params["b"]
            )
            db.add(profile)
        
        # Create initial day state
        today = date.today().isoformat()
        day_state = db_models.DayState(
            athlete_id=athlete.id,
            date=today,
            D_sys=0.0,
            R_mito=0.0,
            E_fat=0.0
        )
        db.add(day_state)
        
        # Create initial per-lift states
        for lift in LiftType:
            lift_state = db_models.LiftDayState(
                athlete_id=athlete.id,
                lift=lift,
                date=today,
                D_l=0.0,
                F_l=1.0,
                C_l=100.0
            )
            db.add(lift_state)
        
        db.commit()
        return athlete
    
    @staticmethod
    def get_athlete(db: Session, athlete_id: int) -> Optional[db_models.Athlete]:
        return db.query(db_models.Athlete).filter(db_models.Athlete.id == athlete_id).first()


class SessionService:
    """
    Strength and endurance session ingestion

    SPRINT A: Uses EngineOrchestrator (modular engines) by default.
    Legacy ConcurrentTrainingModel available via USE_LEGACY_MODEL=true.
    """

    def __init__(self, db: Session):
        self.db = db
        # Sprint A: Use new orchestrator by default (lazy import to avoid circular)
        from app.services.engine_orchestrator import EngineOrchestrator
        self.orchestrator = EngineOrchestrator(db)
        # Legacy model only instantiated if needed
        self._legacy_model = None
    
    @property
    def legacy_model(self):
        """Lazy-load legacy model only when needed"""
        if self._legacy_model is None:
            self._legacy_model = ConcurrentTrainingModel()
        return self._legacy_model
    
    def ingest_strength_session(
        self,
        athlete_id: int,
        lift: LiftType,
        start_time: datetime,
        sets_data: List[schemas.SetData]
    ) -> db_models.StrengthSession:
        """
        Ingest a strength session with VBT data
        
        SPRINT A: Uses EngineOrchestrator (rep_engine + day_engine) by default.
        """
        session_date = start_time.date()
        
        # Convert Pydantic models to dicts for orchestrator
        sets_data_dicts = []
        for set_data in sets_data:
            velocities = [rep.velocity for rep in set_data.reps] if set_data.reps else []
            rest_sec = set_data.reps[0].rest_before if set_data.reps else None
            
            sets_data_dicts.append({
                "load_kg": set_data.weight,
                "reps": len(set_data.reps) if set_data.reps else 0,
                "velocities": velocities,
                "rest_sec": rest_sec
            })
        
        # Use EngineOrchestrator (single source of truth)
        strength_session, day_state, perf_snapshot = self.orchestrator.ingest_strength_session(
            athlete_id=athlete_id,
            lift=lift,
            session_date=session_date,
            sets_data=sets_data_dicts,
            vbt_available=True,
            optional_rpe=None
        )
        
        # Sprint A: Optional legacy path for comparison (never overwrites primary)
        import os
        if os.getenv("USE_LEGACY_MODEL", "false").lower() == "true":
            self._run_legacy_strength_comparison(
                athlete_id, lift, start_time, sets_data, strength_session
            )

        return strength_session
    
    def ingest_endurance_session(
        self,
        athlete_id: int,
        sport: EnduranceSport,
        start_time: datetime,
        duration_minutes: float,
        intensity_type: str
    ) -> db_models.EnduranceSession:
        """
        Ingest an endurance session
        
        SPRINT A: Uses EngineOrchestrator (day_engine) by default.
        """
        session_date = start_time.date()
        
        # Use EngineOrchestrator (single source of truth)
        endurance_session, day_state, perf_snapshot = self.orchestrator.ingest_endurance_session(
            athlete_id=athlete_id,
            session_date=session_date,
            sport=sport,
            duration_minutes=duration_minutes,
            intensity_type=intensity_type,
            power_data=None
        )
        
        # Sprint A: Optional legacy path for comparison
        if USE_LEGACY_MODEL:
            self._run_legacy_endurance_comparison(
                athlete_id, sport, start_time, duration_minutes, intensity_type, endurance_session
            )
        
        return endurance_session
    
    def _run_legacy_strength_comparison(
        self,
        athlete_id: int,
        lift: LiftType,
        start_time: datetime,
        sets_data: List[schemas.SetData],
        primary_session: db_models.StrengthSession
    ) -> None:
        """
        Run legacy model for comparison only - never overwrites primary state.
        Results stored in comparison log for validation.
        """
        # This is a no-op for now - legacy model runs but results not stored
        # Could log to separate table for A/B testing
        pass
    
    def _run_legacy_endurance_comparison(
        self,
        athlete_id: int,
        sport: EnduranceSport,
        start_time: datetime,
        duration_minutes: float,
        intensity_type: str,
        primary_session: db_models.EnduranceSession
    ) -> None:
        """
        Run legacy model for comparison only - never overwrites primary state.
        """
        pass


class DayUpdateService:
    """Daily state updates and computations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.model = ConcurrentTrainingModel()
    
    def update_day_state(self, athlete_id: int, target_date: Optional[date] = None):
        """
        Update all day-level states for an athlete
        This should be run daily (e.g., via cron)
        """
        target_date = target_date or date.today()
        date_str = target_date.isoformat()
        yesterday = date.fromordinal(target_date.toordinal() - 1)
        yesterday_str = yesterday.isoformat()
        
        # Create proper datetime objects for filtering
        yesterday_start = datetime.combine(yesterday, dt_time.min)
        yesterday_end = datetime.combine(target_date, dt_time.min)
        
        # Get yesterday's state or initialize
        yesterday_state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == yesterday_str
        ).first()
        
        if yesterday_state:
            current = DayLevelState(
                date=yesterday_str,
                D_sys=yesterday_state.D_sys,
                R_mito=yesterday_state.R_mito,
                E_fat=yesterday_state.E_fat
            )
        else:
            current = DayLevelState(date=yesterday_str)
        
        # Get yesterday's sessions using proper datetime objects
        strength_sessions = self.db.query(db_models.StrengthSession).filter(
            db_models.StrengthSession.athlete_id == athlete_id,
            db_models.StrengthSession.start_time >= yesterday_start,
            db_models.StrengthSession.start_time < yesterday_end
        ).all()
        
        endurance_sessions = self.db.query(db_models.EnduranceSession).filter(
            db_models.EnduranceSession.athlete_id == athlete_id,
            db_models.EnduranceSession.start_time >= yesterday_start,
            db_models.EnduranceSession.start_time < yesterday_end
        ).all()
        
        # Compute impulses
        strength_impulses = {lift: 0.0 for lift in LiftType}
        u_E_Z2_total = 0.0
        u_E_HIIT_total = 0.0
        u_E_total = 0.0
        
        for session in strength_sessions:
            impulse = self.model.compute_strength_impulse(
                session.tonnage,
                session.avg_intensity,
                1.0,  # velocity factor - simplified
                is_legs=(session.lift in [LiftType.SQUAT, LiftType.DEADLIFT])
            )
            strength_impulses[session.lift] += impulse
        
        for session in endurance_sessions:
            u_E_Z2_total += session.u_E_Z2
            u_E_HIIT_total += session.u_E_HIIT
            u_E_total += session.duration_minutes
        
        # Compute interference factors
        interference = {lift: 0.0 for lift in LiftType}
        for session in endurance_sessions:
            if session.u_E_HIIT > 0:
                for lift in LiftType:
                    interf = self.model.compute_interference_factor(
                        session.sport,
                        12  # Assume 12h before strength - simplified
                    )
                    interference[lift] += interf
        
        # Update domain state
        new_domain = self.model.update_day_state(
            current,
            strength_impulses,
            u_E_Z2_total,
            u_E_HIIT_total,
            u_E_total,
            interference
        )
        new_domain.date = date_str
        
        # Save to DB
        day_state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == date_str
        ).first()
        
        if not day_state:
            day_state = db_models.DayState(athlete_id=athlete_id, date=date_str)
            self.db.add(day_state)
        
        day_state.D_sys = new_domain.D_sys
        day_state.R_mito = new_domain.R_mito
        day_state.E_fat = new_domain.E_fat
        
        # Update per-lift states
        for lift in LiftType:
            lift_state = self.db.query(db_models.LiftDayState).filter(
                db_models.LiftDayState.athlete_id == athlete_id,
                db_models.LiftDayState.lift == lift,
                db_models.LiftDayState.date == date_str
            ).first()
            
            if not lift_state:
                lift_state = db_models.LiftDayState(
                    athlete_id=athlete_id,
                    lift=lift,
                    date=date_str
                )
                self.db.add(lift_state)
            
            lift_state.D_l = new_domain.D_l.get(lift, 0.0)
        
        self.db.commit()
        return day_state


class ReadinessService:
    """Compute readiness scores"""
    
    def __init__(self, db: Session):
        self.db = db
        self.autoreg = Autoregulator(ConcurrentTrainingModel())
    
    def get_readiness(
        self,
        athlete_id: int,
        target_date: Optional[date] = None
    ) -> schemas.ReadinessResponse:
        """
        Get readiness for an athlete on a given date
        """
        target_date = target_date or date.today()
        date_str = target_date.isoformat()
        
        # Get day state
        day_state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == date_str
        ).first()
        
        if not day_state:
            # No state yet - return neutral
            return schemas.ReadinessResponse(
                athlete_id=athlete_id,
                date=date_str,
                overall=100.0,
                per_lift={lift.value: 100.0 for lift in LiftType},
                endurance=100.0,
                explanations=["No training data yet"]
            )
        
        # Get per-lift states
        lift_states = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.date == date_str
        ).all()
        
        # Convert to domain
        domain = DayLevelState(
            date=date_str,
            D_sys=day_state.D_sys,
            R_mito=day_state.R_mito,
            E_fat=day_state.E_fat
        )
        
        for ls in lift_states:
            domain.D_l[ls.lift] = ls.D_l
            domain.F_l[ls.lift] = ls.F_l
            domain.C_l[ls.lift] = ls.C_l
        
        # Compute readiness
        readiness = self.autoreg.compute_readiness(domain)
        
        return schemas.ReadinessResponse(
            athlete_id=athlete_id,
            date=date_str,
            overall=readiness["overall"],
            per_lift=readiness["per_lift"],
            endurance=readiness["endurance"],
            explanations=readiness["explanations"]
        )
    
    def get_lift_trends(
        self,
        athlete_id: int,
        lift: LiftType,
        days: int = 30
    ) -> schemas.LiftTrendResponse:
        """Get trend data for a lift"""
        from datetime import timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        states = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.lift == lift,
            db_models.LiftDayState.date >= start_date.isoformat(),
            db_models.LiftDayState.date <= end_date.isoformat()
        ).order_by(db_models.LiftDayState.date).all()
        
        data = []
        for s in states:
            readiness = (1 - s.D_l) * 100
            data.append(schemas.LiftTrendPoint(
                date=s.date,
                D_l=s.D_l,
                F_l=s.F_l,
                C_l=s.C_l,
                readiness=round(readiness, 1)
            ))
        
        return schemas.LiftTrendResponse(
            athlete_id=athlete_id,
            lift=lift,
            days=days,
            data=data
        )
    
    def get_endurance_trends(
        self,
        athlete_id: int,
        days: int = 30
    ) -> schemas.EnduranceTrendResponse:
        """Get endurance trend data"""
        from datetime import timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        states = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date >= start_date.isoformat(),
            db_models.DayState.date <= end_date.isoformat()
        ).order_by(db_models.DayState.date).all()
        
        data = []
        for s in states:
            readiness = (1 - s.E_fat) * (1 + 0.2 * s.R_mito) * 100
            data.append(schemas.EnduranceTrendPoint(
                date=s.date,
                R_mito=s.R_mito,
                E_fat=s.E_fat,
                readiness=round(max(0, min(100, readiness)), 1)
            ))
        
        return schemas.EnduranceTrendResponse(
            athlete_id=athlete_id,
            days=days,
            data=data
        )


class AutoregulationService:
    """Live autoregulation suggestions"""
    
    def __init__(self, db: Session):
        self.db = db
        self.autoreg = Autoregulator(ConcurrentTrainingModel())
    
    def suggest(
        self,
        request: schemas.AutoregulateRequest
    ) -> schemas.AutoregulateResponse:
        """
        Generate autoregulation suggestion for current set
        """
        # Get athlete's profile
        profile = self.db.query(db_models.LiftProfile).filter(
            db_models.LiftProfile.athlete_id == request.athlete_id,
            db_models.LiftProfile.lift == request.lift
        ).first()
        
        if not profile:
            raise ValueError(f"No profile for lift {request.lift}")
        
        # Get current day state
        today = date.today().isoformat()
        day_state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == request.athlete_id,
            db_models.DayState.date == today
        ).first()
        
        if not day_state:
            day_state = db_models.DayState(
                athlete_id=request.athlete_id,
                date=today,
                D_sys=0.0,
                R_mito=0.0,
                E_fat=0.0
            )
        
        lift_state = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == request.athlete_id,
            db_models.LiftDayState.lift == request.lift,
            db_models.LiftDayState.date == today
        ).first()
        
        if not lift_state:
            # Provide a sensible default capacity so intensity and fatigue reconstruction work
            lift_state = db_models.LiftDayState(
                athlete_id=request.athlete_id,
                lift=request.lift,
                date=today,
                D_l=0.0,
                C_l=100.0
            )
        
        # Initialize rep state from day-level state
        model = ConcurrentTrainingModel()
        domain_day = DayLevelState(
            date=today,
            D_l={request.lift: lift_state.D_l},
            C_l={request.lift: lift_state.C_l},  # Include capacity for intensity calc
            D_sys=day_state.D_sys,
            R_mito=day_state.R_mito,
            E_fat=day_state.E_fat
        )
        
        # Initialize rep state at start of session
        M_base = model.compute_M_base(0, 0)  # Simplified for V1
        rep_state = model.initialize_rep_state(domain_day, request.lift, M_base)
        
        # Compute v_ref for current weight
        v_ref = profile.a - profile.b * request.current_weight
        
        # Get capacity for intensity calculation
        capacity = lift_state.C_l if lift_state.C_l > 0 else 100.0
        
        # Apply actual rep observations from the request to reconstruct within-set fatigue.
        # We don't persist per-rep state server-side, so we approximate by replaying the recent reps.
        recent_velocities = request.recent_v_obs or []
        recent_rests = request.recent_rest_before or []

        # Align rep numbers with the set progression so chi(rep_num, ...) is meaningful.
        # If caller sends only the last N velocities, we map them onto the last N reps completed.
        start_rep_num = max(1, request.current_reps_done - len(recent_velocities) + 1)

        for i, v_obs in enumerate(recent_velocities):
            rep_num = start_rep_num + i
            if i < len(recent_rests):
                rest_before = float(recent_rests[i])
            else:
                rest_before = 0.0 if i == 0 else 2.0  # fallback assumption

            rep_state = model.update_rep_level(
                rep_state,
                request.current_weight,
                v_obs,
                v_ref,
                rep_num,
                rest_before,
                is_legs=(request.lift in [LiftType.SQUAT, LiftType.DEADLIFT]),
                capacity=capacity
            )
        
        # Get suggestion based on updated rep state (with within-set fatigue applied)
        action = self.autoreg.suggest_action(
            rep_state,
            request.target_v_low,
            request.target_v_high,
            request.vl_max,
            v_ref,
            request.current_reps_done,
            request.planned_reps,
            request.current_weight
        )
        
        v_pred = rep_state.predict_velocity(v_ref)
        vl_current = (v_ref - v_pred) / v_ref * 100 if v_pred > 0 else 100
        
        return schemas.AutoregulateResponse(
            continue_set=action["continue"],
            load_change=action["load_change"],
            rest_suggestion=action.get("rest_suggestion"),
            exercise_switch=action.get("exercise_switch"),
            predicted_velocity=round(v_pred, 3),
            current_vl=round(vl_current, 1),
            messages=action["message"]
        )
