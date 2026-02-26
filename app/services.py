"""
Services layer - connects domain model to persistence
"""
from datetime import datetime, date
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.domain.model import (
    ConcurrentTrainingModel, Autoregulator, LiftType, EnduranceSport,
    DayLevelState, RepLevelState, SystemParameters as DomainParams
)
from app import models as db_models
from app import schemas


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
    """Strength and endurance session ingestion"""
    
    def __init__(self, db: Session):
        self.db = db
        self.model = ConcurrentTrainingModel()
    
    def ingest_strength_session(
        self,
        athlete_id: int,
        lift: LiftType,
        start_time: datetime,
        sets_data: List[schemas.SetData]
    ) -> db_models.StrengthSession:
        """
        Ingest a strength session with VBT data
        """
        # Get athlete's lift profile
        profile = self.db.query(db_models.LiftProfile).filter(
            db_models.LiftProfile.athlete_id == athlete_id,
            db_models.LiftProfile.lift == lift
        ).first()
        
        if not profile:
            raise ValueError(f"No profile found for {lift}")
        
        # Get current day state
        today = date.today().isoformat()
        day_state = self._get_or_create_day_state(athlete_id, today)
        lift_day_state = self._get_or_create_lift_day_state(athlete_id, lift, today)
        
        # Convert to domain model
        domain_day = self._to_domain_day_state(day_state, lift_day_state, lift)
        
        # Initialize rep-level state
        M_base = self.model.compute_M_base(0, 0)  # Simplified for V1
        rep_state = self.model.initialize_rep_state(domain_day, lift, M_base)
        
        # Process each set and rep
        rep_log = []
        total_tonnage = 0
        total_intensity = 0
        total_reps = 0
        
        for set_data in sets_data:
            v_ref = profile.a - profile.b * set_data.weight
            
            for rep in set_data.reps:
                # Update rep state
                rep_state = self.model.update_rep_level(
                    rep_state,
                    rep.weight,
                    rep.velocity,
                    v_ref,
                    rep.rep_num,
                    rep.rest_before,
                    is_legs=(lift in [LiftType.SQUAT, LiftType.DEADLIFT])
                )
                
                rep_log.append({
                    "rep": rep.rep_num,
                    "weight": rep.weight,
                    "v_obs": rep.velocity,
                    "v_ref": v_ref,
                    "A_l": rep_state.A_l,
                    "A_sys": rep_state.A_sys,
                    "M": rep_state.M
                })
                
                total_tonnage += rep.weight
                # Estimate intensity from velocity
                est_1rm = profile.a / profile.b if profile.b > 0 else rep.weight * 1.5
                intensity = rep.weight / est_1rm if est_1rm > 0 else 0.7
                total_intensity += intensity
                total_reps += 1
        
        # Create session record
        avg_intensity = total_intensity / total_reps if total_reps > 0 else 0.7
        
        session = db_models.StrengthSession(
            athlete_id=athlete_id,
            lift=lift,
            start_time=start_time,
            tonnage=total_tonnage,
            avg_intensity=avg_intensity,
            raw_data={"sets": [s.model_dump() for s in sets_data]},
            rep_level_log=rep_log
        )
        self.db.add(session)
        self.db.commit()
        
        return session
    
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
        """
        # Split into Z2 and HIIT components
        if intensity_type == "z2":
            u_E_Z2, u_E_HIIT = duration_minutes, 0.0
        elif intensity_type == "hiit":
            u_E_Z2, u_E_HIIT = 0.0, duration_minutes
        else:  # mixed
            u_E_Z2, u_E_HIIT = duration_minutes * 0.3, duration_minutes * 0.7
        
        session = db_models.EnduranceSession(
            athlete_id=athlete_id,
            sport=sport,
            start_time=start_time,
            duration_minutes=duration_minutes,
            intensity_type=intensity_type,
            u_E_Z2=u_E_Z2,
            u_E_HIIT=u_E_HIIT,
            raw_data={"sport": sport.value, "type": intensity_type}
        )
        self.db.add(session)
        self.db.commit()
        
        return session
    
    def _get_or_create_day_state(self, athlete_id: int, date_str: str) -> db_models.DayState:
        """Get or create day state for athlete"""
        state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == date_str
        ).first()
        
        if not state:
            state = db_models.DayState(
                athlete_id=athlete_id,
                date=date_str,
                D_sys=0.0,
                R_mito=0.0,
                E_fat=0.0
            )
            self.db.add(state)
            self.db.commit()
        
        return state
    
    def _get_or_create_lift_day_state(
        self,
        athlete_id: int,
        lift: LiftType,
        date_str: str
    ) -> db_models.LiftDayState:
        """Get or create lift-specific day state"""
        state = self.db.query(db_models.LiftDayState).filter(
            db_models.LiftDayState.athlete_id == athlete_id,
            db_models.LiftDayState.lift == lift,
            db_models.LiftDayState.date == date_str
        ).first()
        
        if not state:
            state = db_models.LiftDayState(
                athlete_id=athlete_id,
                lift=lift,
                date=date_str,
                D_l=0.0,
                F_l=1.0,
                C_l=100.0
            )
            self.db.add(state)
            self.db.commit()
        
        return state
    
    def _to_domain_day_state(
        self,
        day_state: db_models.DayState,
        lift_state: db_models.LiftDayState,
        lift: LiftType
    ) -> DayLevelState:
        """Convert DB state to domain model"""
        return DayLevelState(
            date=day_state.date,
            D_l={lift: lift_state.D_l},
            F_l={lift: lift_state.F_l},
            C_l={lift: lift_state.C_l},
            D_sys=day_state.D_sys,
            R_mito=day_state.R_mito,
            E_fat=day_state.E_fat
        )


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
        yesterday = date.fromordinal(target_date.toordinal() - 1).isoformat()
        
        # Get yesterday's state or initialize
        yesterday_state = self.db.query(db_models.DayState).filter(
            db_models.DayState.athlete_id == athlete_id,
            db_models.DayState.date == yesterday
        ).first()
        
        if yesterday_state:
            current = DayLevelState(
                date=yesterday,
                D_sys=yesterday_state.D_sys,
                R_mito=yesterday_state.R_mito,
                E_fat=yesterday_state.E_fat
            )
        else:
            current = DayLevelState(date=yesterday)
        
        # Get yesterday's sessions
        strength_sessions = self.db.query(db_models.StrengthSession).filter(
            db_models.StrengthSession.athlete_id == athlete_id,
            db_models.StrengthSession.start_time >= f"{yesterday}T00:00:00",
            db_models.StrengthSession.start_time < f"{date_str}T00:00:00"
        ).all()
        
        endurance_sessions = self.db.query(db_models.EnduranceSession).filter(
            db_models.EnduranceSession.athlete_id == athlete_id,
            db_models.EnduranceSession.start_time >= f"{yesterday}T00:00:00",
            db_models.EnduranceSession.start_time < f"{date_str}T00:00:00"
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
            lift_state = db_models.LiftDayState(
                athlete_id=request.athlete_id,
                lift=request.lift,
                date=today,
                D_l=0.0
            )
        
        # Initialize rep state
        model = ConcurrentTrainingModel()
        domain_day = DayLevelState(
            date=today,
            D_l={request.lift: lift_state.D_l},
            D_sys=day_state.D_sys,
            R_mito=day_state.R_mito,
            E_fat=day_state.E_fat
        )
        
        rep_state = model.initialize_rep_state(domain_day, request.lift)
        
        # Compute v_ref
        v_ref = profile.a - profile.b * request.current_weight
        
        # Get suggestion
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
