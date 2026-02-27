"""
Sprint V1: Replay Runner - Chronological retrospective replay

Replays historical sessions and logs prediction errors.
"""
import json
import csv
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.eval.validation import (
    compute_rep_level_metrics,
    compute_day_level_strength_metrics,
    compute_trend_classification_metrics,
    compute_endurance_classification_metrics,
    predict_perf_y_from_readiness,
    ValidationReport,
)
from app.eval.baselines import BaselineVelocityThreshold, BaselineBanister, BaselineEndurance
from app.services.engine_orchestrator import EngineOrchestrator
from app.domain.rep_engine import simulate_strength_session, LiftVelocityProfile, SessionInput, SetInput, RepEngineParams
from app.domain.day_engine import PerLiftState
from app import models
from app.types import LiftType, EnduranceSport


class ReplayRunner:
    """
    Replay historical sessions chronologically and log prediction errors.
    """
    
    def __init__(self, db: Session, artifacts_dir: str = "./artifacts"):
        self.db = db
        self.orchestrator = EngineOrchestrator(db)
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Baselines
        self.baseline_a = BaselineVelocityThreshold(window_days=7)
        self.baseline_b = BaselineBanister()
        self.baseline_endurance = BaselineEndurance(window_days=7)
        
        # Accumulated logs
        self.rep_errors: List[Dict] = []
        self.day_errors: List[Dict] = []
        self.trend_evals: List[Dict] = []
    
    def replay(
        self,
        athlete_id: int,
        date_from: date,
        date_to: date,
        dry_run: bool = True
    ) -> ValidationReport:
        """
        Replay all sessions for athlete in date range.
        
        Args:
            athlete_id: Athlete to replay
            date_from: Start date (inclusive)
            date_to: End date (inclusive)
            dry_run: If True, don't write to DB (use direct domain calls)
        
        Returns:
            ValidationReport with computed metrics
        """
        # Load all sessions in range
        strength_sessions = self._load_strength_sessions(athlete_id, date_from, date_to)
        endurance_sessions = self._load_endurance_sessions(athlete_id, date_from, date_to)
        
        # Merge and sort chronologically
        all_sessions = []
        for s in strength_sessions:
            all_sessions.append(("strength", s.start_time.date(), s))
        for e in endurance_sessions:
            all_sessions.append(("endurance", e.start_time.date(), e))
        
        all_sessions.sort(key=lambda x: (x[1], x[0]))  # Sort by date, then type
        
        # Replay each session
        for session_type, session_date, session in all_sessions:
            if session_type == "strength":
                self._replay_strength_session(
                    athlete_id, session, dry_run
                )
            else:
                self._replay_endurance_session(
                    athlete_id, session, dry_run
                )
        
        # Compute and return metrics
        return self._compute_report(athlete_id, date_from, date_to)
    
    def _load_strength_sessions(
        self, athlete_id: int, date_from: date, date_to: date
    ) -> List[models.StrengthSession]:
        """Load strength sessions in date range."""
        return self.db.query(models.StrengthSession).filter(
            models.StrengthSession.athlete_id == athlete_id,
            models.StrengthSession.start_time >= datetime.combine(date_from, datetime.min.time()),
            models.StrengthSession.start_time <= datetime.combine(date_to, datetime.max.time())
        ).order_by(models.StrengthSession.start_time).all()
    
    def _load_endurance_sessions(
        self, athlete_id: int, date_from: date, date_to: date
    ) -> List[models.EnduranceSession]:
        """Load endurance sessions in date range."""
        return self.db.query(models.EnduranceSession).filter(
            models.EnduranceSession.athlete_id == athlete_id,
            models.EnduranceSession.start_time >= datetime.combine(date_from, datetime.min.time()),
            models.EnduranceSession.start_time <= datetime.combine(date_to, datetime.max.time())
        ).order_by(models.EnduranceSession.start_time).all()
    
    def _replay_strength_session(
        self,
        athlete_id: int,
        session: models.StrengthSession,
        dry_run: bool
    ):
        """Replay a strength session and log predictions."""
        session_date = session.start_time.date()
        lift = session.lift
        
        # Get predictions BEFORE applying
        day_state = self.orchestrator.get_day_state_snapshot(athlete_id, session_date)
        
        # Model prediction
        if day_state:
            lift_state = day_state.per_lift.get(lift.value, PerLiftState())
            readiness_model = self._compute_readiness_from_state(lift_state, day_state)
            pred_perf_y_model = predict_perf_y_from_readiness(readiness_model)
        else:
            pred_perf_y_model = 0.85  # Default
        
        # Baseline A prediction
        pred_perf_y_a = self.baseline_a.predict_perf_y(lift.value, session_date)
        
        # Baseline B prediction
        pred_perf_y_b = self.baseline_b.predict_perf_y(lift.value)
        
        # Extract raw data
        raw_data = session.raw_data or {}
        sets_data = raw_data.get("sets", [])
        
        # Compute rep-level predictions if VBT data available
        if sets_data and self._has_vbt_data(sets_data):
            self._evaluate_rep_predictions(athlete_id, lift, session_date, sets_data)
        
        # Apply session (or simulate)
        if not dry_run:
            # Use orchestrator to apply
            sets_converted = self._convert_sets_for_orchestrator(sets_data)
            try:
                self.orchestrator.ingest_strength_session(
                    athlete_id=athlete_id,
                    lift=lift,
                    session_date=session_date,
                    sets_data=sets_converted,
                    vbt_available=True
                )
            except Exception as e:
                # Log error but continue
                print(f"Warning: failed to apply session {session.id}: {e}")
        
        # Observe actual perf_y from session
        observed_perf_y = self._extract_observed_perf_y(sets_data)
        
        # Log day-level error
        if observed_perf_y:
            self.day_errors.append({
                "date": session_date.isoformat(),
                "lift": lift.value,
                "predicted_model": pred_perf_y_model,
                "predicted_baseline_a": pred_perf_y_a,
                "predicted_baseline_b": pred_perf_y_b,
                "observed": observed_perf_y,
            })
            
            # Update baselines with observation
            self.baseline_a.add_observation(lift.value, session_date, observed_perf_y)
            self.baseline_b.update(
                lift.value, session_date,
                tonnage=session.tonnage,
                intensity=session.avg_intensity
            )
    
    def _replay_endurance_session(
        self,
        athlete_id: int,
        session: models.EnduranceSession,
        dry_run: bool
    ):
        """Replay an endurance session and log predictions."""
        session_date = session.start_time.date()
        
        # Model prediction
        day_state = self.orchestrator.get_day_state_snapshot(athlete_id, session_date)
        if day_state:
            readiness_endurance = 1.0 - day_state.E_fat
            predicted_stable_model = readiness_endurance > 0.65
        else:
            predicted_stable_model = True
        
        # Baseline prediction
        load_proxy = session.duration_minutes * (5.0 / 10.0)  # Assume RPE 5 if not available
        predicted_stable_baseline = self.baseline_endurance.predict_stable(session_date)
        
        # Apply session
        if not dry_run:
            try:
                self.orchestrator.ingest_endurance_session(
                    athlete_id=athlete_id,
                    session_date=session_date,
                    sport=session.sport,
                    duration_minutes=session.duration_minutes,
                    intensity_type=session.intensity_type or "z2"
                )
            except Exception as e:
                print(f"Warning: failed to apply endurance session {session.id}: {e}")
        
        # Log for trend evaluation (simplified)
        self.baseline_endurance.add_observation(session_date, load_proxy)
    
    def _evaluate_rep_predictions(
        self,
        athlete_id: int,
        lift: LiftType,
        session_date: date,
        sets_data: List[Dict]
    ):
        """Evaluate rep-level velocity predictions."""
        # Get profile
        profile_db = self.db.query(models.LiftProfile).filter(
            models.LiftProfile.athlete_id == athlete_id,
            models.LiftProfile.lift == lift
        ).first()
        
        if not profile_db:
            return
        
        profile = LiftVelocityProfile(
            lift=lift.value,
            a=profile_db.a,
            b=profile_db.b
        )
        
        # Step through each set
        for set_idx, set_data in enumerate(sets_data):
            reps = set_data.get("reps", [])
            if len(reps) < 2:
                continue
            
            # Initialize state at start of set
            # Simplified: start fresh for each set
            from app.domain.rep_engine import RepState
            params = RepEngineParams()
            state = RepState(
                A_local_init={lift.value: 1.0},
                A_sys_init=1.0,
                M_init=0.0,
                params=params
            )
            
            v_ref = profile.a - profile.b * set_data.get("weight", 0)
            
            # For each rep starting from 2nd
            for rep_idx in range(1, len(reps)):
                # Predict velocity for this rep (before observing)
                v_pred = state.predict_velocity(v_ref, lift.value)
                
                # Get observed velocity
                v_obs = reps[rep_idx].get("velocity", 0)
                
                # Log error
                self.rep_errors.append({
                    "date": session_date.isoformat(),
                    "lift": lift.value,
                    "set": set_idx,
                    "rep": rep_idx,
                    "v_pred": round(v_pred, 4),
                    "v_obs": round(v_obs, 4),
                    "error": round(v_obs - v_pred, 4),
                })
                
                # Update state with observed velocity
                y = v_obs / v_ref if v_ref > 0 else 1.0
                state.apply_rep(lift.value, set_data.get("weight", 0), y, rep_idx)
    
    def _compute_readiness_from_state(self, lift_state: PerLiftState, day_state) -> float:
        """Compute readiness from day state."""
        # Simple readiness: 1 - fatigue factors
        return max(0.0, min(1.0, 1.0 - lift_state.D_l - 0.5 * day_state.D_sys))
    
    def _has_vbt_data(self, sets_data: List[Dict]) -> bool:
        """Check if sets have velocity data."""
        for s in sets_data:
            reps = s.get("reps", [])
            for r in reps:
                if "velocity" in r:
                    return True
        return False
    
    def _convert_sets_for_orchestrator(self, sets_data: List[Dict]) -> List[Dict]:
        """Convert raw sets to orchestrator format."""
        converted = []
        for s in sets_data:
            reps = s.get("reps", [])
            converted.append({
                "load_kg": s.get("weight", 0),
                "reps": len(reps),
                "velocities": [r.get("velocity", 0) for r in reps],
                "rest_sec": reps[0].get("rest_before", 0) if reps else None,
            })
        return converted
    
    def _extract_observed_perf_y(self, sets_data: List[Dict]) -> Optional[float]:
        """Extract observed perf_y from best quality set."""
        best_perf_y = None
        
        for set_data in sets_data:
            reps = set_data.get("reps", [])
            if len(reps) < 2 or len(reps) > 6:
                continue  # Skip sets with too few or too many reps
            
            # Compute y for first 2 reps
            v_refs = []
            v_obs_list = []
            for rep in reps[:2]:
                v_obs = rep.get("velocity", 0)
                # Estimate v_ref from load (simplified)
                # This is approximate; better would be to use profile
                v_obs_list.append(v_obs)
            
            if len(v_obs_list) >= 2 and v_obs_list[0] > 0:
                # Simple proxy: ratio of rep 2 to rep 1
                perf_y = v_obs_list[1] / v_obs_list[0]
                if best_perf_y is None or perf_y > best_perf_y:
                    best_perf_y = perf_y
        
        return best_perf_y
    
    def _compute_report(
        self,
        athlete_id: int,
        date_from: date,
        date_to: date
    ) -> ValidationReport:
        """Compute final validation report."""
        report = ValidationReport(
            athlete_id=athlete_id,
            date_range=(date_from, date_to)
        )
        
        # Rep-level metrics
        if self.rep_errors:
            predictions = [e["v_pred"] for e in self.rep_errors]
            observed = [e["v_obs"] for e in self.rep_errors]
            metrics = compute_rep_level_metrics(predictions, observed)
            report.rep_level_rmse = metrics.rmse
            report.rep_level_mae = metrics.mae
        
        # Day-level metrics (strength)
        if self.day_errors:
            pred_model = [e["predicted_model"] for e in self.day_errors]
            pred_a = [e["predicted_baseline_a"] for e in self.day_errors]
            pred_b = [e["predicted_baseline_b"] for e in self.day_errors]
            obs = [e["observed"] for e in self.day_errors]
            
            report.day_level_mae_model = compute_day_level_strength_metrics(pred_model, obs).mae
            report.day_level_mae_baseline_a = compute_day_level_strength_metrics(pred_a, obs).mae
            report.day_level_mae_baseline_b = compute_day_level_strength_metrics(pred_b, obs).mae
        
        return report
    
    def write_artifacts(self, run_id: str):
        """Write all accumulated logs to artifacts directory."""
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Rep errors CSV - deterministic ordering
        if self.rep_errors:
            # Sort by date, lift, set, rep for determinism
            sorted_rep_errors = sorted(
                self.rep_errors,
                key=lambda x: (x.get("date", ""), x.get("lift", ""), x.get("set", 0), x.get("rep", 0))
            )
            with open(run_dir / "rep_errors.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=sorted_rep_errors[0].keys())
                writer.writeheader()
                writer.writerows(sorted_rep_errors)
        
        # Day errors CSV - deterministic ordering
        if self.day_errors:
            sorted_day_errors = sorted(
                self.day_errors,
                key=lambda x: (x.get("date", ""), x.get("lift", ""))
            )
            with open(run_dir / "day_errors.csv", "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=sorted_day_errors[0].keys())
                writer.writeheader()
                writer.writerows(sorted_day_errors)
        
        # Write summary JSON with deterministic formatting
        summary = self._compute_summary_dict()
        with open(run_dir / "summary.json", "w") as f:
            json.dump(summary, f, sort_keys=True, separators=(',', ':'))
        
        print(f"Artifacts written to {run_dir}")
    
    def _compute_summary_dict(self) -> Dict:
        """Compute deterministic summary dictionary."""
        summary = {
            "n_rep_errors": len(self.rep_errors),
            "n_day_errors": len(self.day_errors),
            "rep_metrics": {},
            "day_metrics": {},
        }
        
        if self.rep_errors:
            predictions = [e["v_pred"] for e in self.rep_errors]
            observed = [e["v_obs"] for e in self.rep_errors]
            metrics = compute_rep_level_metrics(predictions, observed)
            summary["rep_metrics"] = {
                "rmse": round(metrics.rmse, 6),
                "mae": round(metrics.mae, 6),
                "n_samples": metrics.n_samples,
            }
        
        if self.day_errors:
            pred_model = [e["predicted_model"] for e in self.day_errors]
            pred_a = [e["predicted_baseline_a"] for e in self.day_errors]
            pred_b = [e["predicted_baseline_b"] for e in self.day_errors]
            obs = [e["observed"] for e in self.day_errors]
            
            summary["day_metrics"] = {
                "mae_model": round(compute_day_level_strength_metrics(pred_model, obs).mae, 6),
                "mae_baseline_a": round(compute_day_level_strength_metrics(pred_a, obs).mae, 6),
                "mae_baseline_b": round(compute_day_level_strength_metrics(pred_b, obs).mae, 6),
            }
        
        return summary
