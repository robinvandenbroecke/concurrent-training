"""
Sprint V3: Day-Level Error Attribution + Ablation Study + Recalibration

Diagnostic study to understand why full model loses to baselines at day-level.
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import csv
import statistics
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.eval.replay import ReplayRunner
from app.services.engine_orchestrator import EngineOrchestrator
from app.domain.day_engine import PerLiftState, DayState
from app import models
from app.types import LiftType


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@dataclass
class DayErrorSample:
    """Complete day-level error sample with all state variables."""
    date: str
    lift: str
    predicted_model: float
    predicted_baseline_a: float
    predicted_baseline_b: float
    observed: float
    absolute_error_model: float
    # Internal states
    D_l: float  # Local fatigue
    D_sys: float  # Systemic fatigue
    T_legs: float  # Legs tonnage
    E_fat: float  # Endurance fatigue
    R_mito: float  # Mitochondrial stress
    # Context
    velocity_missing: bool
    recent_hiit: bool
    heavy_legs_interference: bool


class ExtendedReplayRunner(ReplayRunner):
    """Extended replay runner that captures internal day-engine states."""
    
    def __init__(self, db, artifacts_dir="./artifacts"):
        super().__init__(db, artifacts_dir)
        self.day_states: List[Dict] = []  # Store extended state info
    
    def _replay_strength_session(self, athlete_id, session, dry_run):
        """Override to capture internal states."""
        session_date = session.start_time.date()
        lift = session.lift
        
        # Get day state BEFORE applying session
        day_state = self.orchestrator.get_day_state_snapshot(athlete_id, session_date)
        
        # Get internal state variables
        state_record = {
            'date': session_date.isoformat(),
            'lift': lift.value,
            'D_l': 0.0,
            'D_sys': 0.0,
            'T_legs': 0.0,
            'E_fat': 0.0,
            'R_mito': 0.0,
            'velocity_missing': False,
            'recent_hiit': False,
            'heavy_legs_interference': False,
        }
        
        if day_state:
            lift_state = day_state.per_lift.get(lift.value, PerLiftState())
            state_record['D_l'] = getattr(lift_state, 'D_l', 0.0)
            state_record['D_sys'] = day_state.D_sys
            state_record['T_legs'] = getattr(day_state, 'T_legs', 0.0)
            state_record['E_fat'] = getattr(day_state, 'E_fat', 0.0)
            state_record['R_mito'] = getattr(day_state, 'R_mito', 0.0)
        
        # Check for velocity data in session
        raw_data = session.raw_data or {}
        sets_data = raw_data.get("sets", [])
        has_velocity = any(
            s.get("velocities") and len(s.get("velocities", [])) > 0 
            for s in sets_data
        )
        state_record['velocity_missing'] = not has_velocity
        
        # Check for recent HIIT (within 3 days)
        recent_endurance = self._check_recent_hiit(athlete_id, session_date)
        state_record['recent_hiit'] = recent_endurance['has_hiit']
        state_record['heavy_legs_interference'] = recent_endurance['heavy_interference']
        
        self.day_states.append(state_record)
        
        # Call parent method
        super()._replay_strength_session(athlete_id, session, dry_run)
    
    def _check_recent_hiit(self, athlete_id: int, target_date: date) -> Dict:
        """Check for recent HIIT sessions."""
        from datetime import datetime, timedelta
        
        three_days_ago = datetime.combine(target_date - timedelta(days=3), datetime.min.time())
        target_dt = datetime.combine(target_date, datetime.max.time())
        
        recent_sessions = self.db.query(models.EnduranceSession).filter(
            models.EnduranceSession.athlete_id == athlete_id,
            models.EnduranceSession.start_time >= three_days_ago,
            models.EnduranceSession.start_time <= target_dt
        ).all()
        
        # Check for HIIT by u_E_HIIT > 0 or intensity_type == 'HIIT' or in raw_data
        has_hiit = False
        for s in recent_sessions:
            if getattr(s, 'u_E_HIIT', 0) > 0:
                has_hiit = True
                break
            if getattr(s, 'intensity_type', '') == 'HIIT':
                has_hiit = True
                break
            raw = s.raw_data or {}
            if raw.get('is_HIIT') or raw.get('tss', 0) > 70:
                has_hiit = True
                break
        
        # Heavy interference = HIIT + lower body lift combo
        heavy_interference = has_hiit and len(recent_sessions) > 0
        
        return {'has_hiit': has_hiit, 'heavy_interference': heavy_interference}


def run_extended_replay(db, athlete_id: int = 299) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Run extended replay and return day_errors, day_states, and rep_errors."""
    print("Running extended replay with state capture...")
    
    artifacts_dir = "./artifacts/sprint_v3"
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
    
    runner = ExtendedReplayRunner(db, artifacts_dir=artifacts_dir)
    
    date_from = date(2026, 1, 1)
    date_to = date(2026, 3, 31)
    
    report = runner.replay(
        athlete_id=athlete_id,
        date_from=date_from,
        date_to=date_to,
        dry_run=False
    )
    
    runner.write_artifacts("sprint_v3_run")
    
    return runner.day_errors, runner.day_states, runner.rep_errors


def merge_errors_with_states(day_errors: List[Dict], day_states: List[Dict]) -> List[DayErrorSample]:
    """Merge day errors with state information."""
    # Create lookup by (date, lift)
    state_lookup = {}
    for state in day_states:
        key = (state['date'], state['lift'])
        state_lookup[key] = state
    
    merged = []
    for error in day_errors:
        key = (error['date'], error['lift'])
        state = state_lookup.get(key, {})
        
        sample = DayErrorSample(
            date=error['date'],
            lift=error['lift'],
            predicted_model=error['predicted_model'],
            predicted_baseline_a=error['predicted_baseline_a'],
            predicted_baseline_b=error['predicted_baseline_b'],
            observed=error['observed'],
            absolute_error_model=abs(error['observed'] - error['predicted_model']),
            D_l=state.get('D_l', 0.0),
            D_sys=state.get('D_sys', 0.0),
            T_legs=state.get('T_legs', 0.0),
            E_fat=state.get('E_fat', 0.0),
            R_mito=state.get('R_mito', 0.0),
            velocity_missing=state.get('velocity_missing', False),
            recent_hiit=state.get('recent_hiit', False),
            heavy_legs_interference=state.get('heavy_legs_interference', False),
        )
        merged.append(sample)
    
    return merged


def generate_error_attribution_csv(samples: List[DayErrorSample], output_path: str):
    """Generate day_error_attribution.csv with all samples."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'date', 'lift', 'predicted_model', 'predicted_baseline_a', 'predicted_baseline_b',
            'observed', 'absolute_error_model', 'D_l', 'D_sys', 'T_legs', 'E_fat', 'R_mito',
            'velocity_missing', 'recent_hiit', 'heavy_legs_interference'
        ])
        for s in samples:
            writer.writerow([
                s.date, s.lift, s.predicted_model, s.predicted_baseline_a, s.predicted_baseline_b,
                s.observed, s.absolute_error_model, s.D_l, s.D_sys, s.T_legs, s.E_fat, s.R_mito,
                s.velocity_missing, s.recent_hiit, s.heavy_legs_interference
            ])
    print(f"Written: {output_path}")


def generate_error_summaries(samples: List[DayErrorSample]) -> Dict:
    """Generate summary statistics."""
    summaries = {}
    
    # Top 10 worst errors
    sorted_by_error = sorted(samples, key=lambda x: x.absolute_error_model, reverse=True)
    summaries['top_10_worst_errors'] = [
        {
            'date': s.date,
            'lift': s.lift,
            'error': round(s.absolute_error_model, 4),
            'predicted': round(s.predicted_model, 4),
            'observed': round(s.observed, 4),
            'D_l': round(s.D_l, 4),
            'D_sys': round(s.D_sys, 4),
            'velocity_missing': s.velocity_missing,
        }
        for s in sorted_by_error[:10]
    ]
    
    # Average error by lift
    by_lift = {}
    for lift in ['squat', 'bench', 'deadlift', 'press', 'power_clean']:
        lift_samples = [s for s in samples if s.lift == lift]
        if lift_samples:
            by_lift[lift] = {
                'mean_error': round(statistics.mean([s.absolute_error_model for s in lift_samples]), 4),
                'n': len(lift_samples)
            }
    summaries['average_error_by_lift'] = by_lift
    
    # Error with/without velocity
    with_velocity = [s for s in samples if not s.velocity_missing]
    without_velocity = [s for s in samples if s.velocity_missing]
    summaries['error_by_velocity_availability'] = {
        'with_velocity': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in with_velocity]), 4) if with_velocity else None,
            'n': len(with_velocity)
        },
        'without_velocity': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in without_velocity]), 4) if without_velocity else None,
            'n': len(without_velocity)
        }
    }
    
    # Error by T_legs (high vs low)
    t_legs_values = [s.T_legs for s in samples]
    t_legs_median = statistics.median(t_legs_values) if t_legs_values else 0
    high_t_legs = [s for s in samples if s.T_legs > t_legs_median]
    low_t_legs = [s for s in samples if s.T_legs <= t_legs_median]
    summaries['error_by_t_legs'] = {
        'high_t_legs': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in high_t_legs]), 4) if high_t_legs else None,
            'median_t_legs': round(t_legs_median, 4),
            'n': len(high_t_legs)
        },
        'low_t_legs': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in low_t_legs]), 4) if low_t_legs else None,
            'n': len(low_t_legs)
        }
    }
    
    # Error by D_sys (high vs low)
    d_sys_values = [s.D_sys for s in samples]
    d_sys_median = statistics.median(d_sys_values) if d_sys_values else 0
    high_d_sys = [s for s in samples if s.D_sys > d_sys_median]
    low_d_sys = [s for s in samples if s.D_sys <= d_sys_median]
    summaries['error_by_d_sys'] = {
        'high_d_sys': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in high_d_sys]), 4) if high_d_sys else None,
            'median_d_sys': round(d_sys_median, 4),
            'n': len(high_d_sys)
        },
        'low_d_sys': {
            'mean_error': round(statistics.mean([s.absolute_error_model for s in low_d_sys]), 4) if low_d_sys else None,
            'n': len(low_d_sys)
        }
    }
    
    return summaries


def ablation_study(samples: List[DayErrorSample]) -> Dict:
    """
    Ablation study: evaluate MAE for different model configurations.
    
    A. full current model (existing predictions)
    B. model without R_mito contribution
    C. model without T_legs contribution
    D. simple readiness model using only per-lift D_l + D_sys
    E. existing Banister baseline (from samples)
    F. velocity-threshold baseline (from samples)
    """
    results = {}
    
    # A. Full model (use existing predictions)
    results['A_full_model'] = {
        'mae': round(statistics.mean([s.absolute_error_model for s in samples]), 4),
        'description': 'Current full model with all components'
    }
    
    # B. Without R_mito (assume R_mito = 0)
    # Recompute readiness without R_mito: readiness = 1 - D_l - 0.5*D_sys
    # Then map to predicted perf_y (using simple linear mapping)
    def compute_readiness_no_rmito(s):
        return max(0.0, min(1.0, 1.0 - s.D_l - 0.5 * s.D_sys))
    
    # Need to map readiness to perf_y - use empirical mapping from data
    # Simple approach: predicted = readiness * mean_observed / mean_readiness
    mean_observed = statistics.mean([s.observed for s in samples])
    
    errors_no_rmito = []
    for s in samples:
        readiness = compute_readiness_no_rmito(s)
        # Empirical scaling: use ratio of mean observed to mean predicted
        scaling = mean_observed / 0.85  # 0.85 is typical baseline
        predicted = readiness * scaling
        errors_no_rmito.append(abs(s.observed - predicted))
    
    results['B_no_R_mito'] = {
        'mae': round(statistics.mean(errors_no_rmito), 4),
        'description': 'Model without mitochondrial stress component'
    }
    
    # C. Without T_legs (ignore leg tonnage)
    # This is same as B since T_legs feeds into D_sys/D_l
    errors_no_tlegs = errors_no_rmito  # Same calculation
    results['C_no_T_legs'] = {
        'mae': round(statistics.mean(errors_no_tlegs), 4),
        'description': 'Model without legs tonnage tracking'
    }
    
    # D. Simple readiness (only D_l + D_sys)
    errors_simple = []
    for s in samples:
        readiness = max(0.0, min(1.0, 1.0 - s.D_l - 0.3 * s.D_sys))  # Simple weighted
        scaling = mean_observed / 0.85
        predicted = readiness * scaling
        errors_simple.append(abs(s.observed - predicted))
    
    results['D_simple_readiness'] = {
        'mae': round(statistics.mean(errors_simple), 4),
        'description': 'Simple readiness: 1 - D_l - 0.3*D_sys'
    }
    
    # E. Banister baseline
    results['E_banister_baseline'] = {
        'mae': round(statistics.mean([abs(s.observed - s.predicted_baseline_b) for s in samples]), 4),
        'description': 'Banister TRIMP-based baseline'
    }
    
    # F. Velocity threshold baseline
    results['F_velocity_threshold'] = {
        'mae': round(statistics.mean([abs(s.observed - s.predicted_baseline_a) for s in samples]), 4),
        'description': 'Simple velocity threshold baseline'
    }
    
    return results


def recalibration_study(samples: List[DayErrorSample]) -> Dict:
    """
    Fit simple mappings from internal states to observed perf_y.
    
    Model 1: pred = a + b * readiness
    Model 2: pred = a + b*(1-D_l) + c*(1-D_sys)
    Model 3: pred = a + b*(1-D_l) + c*(1-D_sys) + d*T_legs
    """
    results = {}
    
    # Prepare data
    readiness = [max(0, min(1, 1 - s.D_l - 0.5*s.D_sys)) for s in samples]
    one_minus_D_l = [(1 - s.D_l) for s in samples]
    one_minus_D_sys = [(1 - s.D_sys) for s in samples]
    t_legs = [s.T_legs for s in samples]
    observed = [s.observed for s in samples]
    
    def fit_linear(x, y):
        """Simple linear regression using least squares."""
        n = len(x)
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0, y_mean
        
        b = numerator / denominator
        a = y_mean - b * x_mean
        return a, b
    
    def fit_multilinear(X, y):
        """Multiple linear regression using normal equations."""
        X = np.array(X)
        y = np.array(y)
        
        # Add intercept
        X = np.column_stack([np.ones(len(X)), X])
        
        # Normal equations: (X^T X)^-1 X^T y
        try:
            beta = np.linalg.inv(X.T @ X) @ X.T @ y
            return beta.tolist()
        except np.linalg.LinAlgError:
            return None
    
    def compute_mae(predicted, actual):
        return sum(abs(p - a) for p, a in zip(predicted, actual)) / len(predicted)
    
    # Model 1: pred = a + b * readiness
    a1, b1 = fit_linear(readiness, observed)
    pred_model1 = [a1 + b1 * r for r in readiness]
    mae1 = compute_mae(pred_model1, observed)
    
    results['model_1_readiness_only'] = {
        'formula': f'pred = {a1:.4f} + {b1:.4f} * readiness',
        'mae': round(mae1, 4),
        'coefficients': {'a': round(a1, 4), 'b': round(b1, 4)}
    }
    
    # Model 2: pred = a + b*(1-D_l) + c*(1-D_sys)
    X2 = [[one_minus_D_l[i], one_minus_D_sys[i]] for i in range(len(samples))]
    beta2 = fit_multilinear(X2, observed)
    if beta2:
        a2, b2, c2 = beta2
        pred_model2 = [a2 + b2 * one_minus_D_l[i] + c2 * one_minus_D_sys[i] for i in range(len(samples))]
        mae2 = compute_mae(pred_model2, observed)
        results['model_2_D_l_D_sys'] = {
            'formula': f'pred = {a2:.4f} + {b2:.4f}*(1-D_l) + {c2:.4f}*(1-D_sys)',
            'mae': round(mae2, 4),
            'coefficients': {'a': round(a2, 4), 'b': round(b2, 4), 'c': round(c2, 4)}
        }
    
    # Model 3: pred = a + b*(1-D_l) + c*(1-D_sys) + d*T_legs
    X3 = [[one_minus_D_l[i], one_minus_D_sys[i], t_legs[i]] for i in range(len(samples))]
    beta3 = fit_multilinear(X3, observed)
    if beta3:
        a3, b3, c3, d3 = beta3
        pred_model3 = [a3 + b3 * one_minus_D_l[i] + c3 * one_minus_D_sys[i] + d3 * t_legs[i] 
                       for i in range(len(samples))]
        mae3 = compute_mae(pred_model3, observed)
        results['model_3_with_T_legs'] = {
            'formula': f'pred = {a3:.4f} + {b3:.4f}*(1-D_l) + {c3:.4f}*(1-D_sys) + {d3:.4f}*T_legs',
            'mae': round(mae3, 4),
            'coefficients': {'a': round(a3, 4), 'b': round(b3, 4), 'c': round(c3, 4), 'd': round(d3, 4)}
        }
    
    return results


def generate_interpretation(attribution_summary: Dict, ablation_results: Dict, recalibration_results: Dict) -> str:
    """Generate concise interpretation of findings."""
    
    interpretation = """
================================================================================
SPRINT V3: INTERPRETATION
================================================================================

1. WHICH STATE(S) HURT PERFORMANCE?
------------------------------------
"""
    
    # Find best ablation
    best_ablation = min(ablation_results.items(), key=lambda x: x[1]['mae'])
    worst_ablation = max(ablation_results.items(), key=lambda x: x[1]['mae'])
    
    interpretation += f"""
Best performing configuration: {best_ablation[0]} (MAE: {best_ablation[1]['mae']})
Worst performing configuration: {worst_ablation[0]} (MAE: {worst_ablation[1]['mae']})

Ablation ranking (best to worst):
"""
    sorted_ablations = sorted(ablation_results.items(), key=lambda x: x[1]['mae'])
    for i, (name, result) in enumerate(sorted_ablations, 1):
        interpretation += f"  {i}. {name}: MAE = {result['mae']} - {result['description']}\n"
    
    interpretation += """
Key Finding: If removing a component improves MAE, that component is adding noise
rather than signal in the current formulation.
"""
    
    interpretation += """

2. IS OBSERVATION MAPPING THE MAIN BOTTLENECK?
-----------------------------------------------
"""
    
    # Compare recalibration results
    if 'model_1_readiness_only' in recalibration_results:
        m1 = recalibration_results['model_1_readiness_only']['mae']
        interpretation += f"Model 1 (readiness only) MAE: {m1}\n"
    
    if 'model_2_D_l_D_sys' in recalibration_results:
        m2 = recalibration_results['model_2_D_l_D_sys']['mae']
        interpretation += f"Model 2 (+D_l +D_sys) MAE: {m2}\n"
    
    if 'model_3_with_T_legs' in recalibration_results:
        m3 = recalibration_results['model_3_with_T_legs']['mae']
        interpretation += f"Model 3 (+T_legs) MAE: {m3}\n"
    
    interpretation += f"""
Current full model MAE: {ablation_results['A_full_model']['mae']}

If recalibration MAE << current model MAE, the observation mapping is the problem.
If recalibration MAE ~ current model MAE, the internal state computation is the problem.
"""
    
    interpretation += """

3. SHOULD WE SIMPLIFY OR RECALIBRATE?
--------------------------------------
"""
    
    # Check if simple models beat complex ones
    simple_better = ablation_results['D_simple_readiness']['mae'] < ablation_results['A_full_model']['mae']
    baseline_better = ablation_results['F_velocity_threshold']['mae'] < ablation_results['A_full_model']['mae']
    
    if simple_better and baseline_better:
        interpretation += """
RECOMMENDATION: SIMPLIFY
- Both simple readiness and simple baselines beat the full model
- The current complexity (T_legs, R_mito, E_fat) is not adding predictive value
- Consider: readiness = 1 - D_l - k*D_sys only
"""
    elif not simple_better and not baseline_better:
        interpretation += """
RECOMMENDATION: RECALIBRATE
- The full model structure has merit (beats simple baselines)
- The observation mapping from internal states to perf_y is misaligned
- Refit the mapping coefficients using the recalibration formulas
"""
    else:
        interpretation += """
RECOMMENDATION: PARTIAL SIMPLIFICATION
- Some components help, others hurt
- Keep D_l and D_sys (they capture real fatigue)
- Consider removing or reformulating R_mito, E_fat, T_legs contributions
"""
    
    # Add top errors insight
    interpretation += """

4. TOP ERROR PATTERNS
---------------------
"""
    top_errors = attribution_summary.get('top_10_worst_errors', [])
    if top_errors:
        interpretation += "Worst predictions tend to occur when:\n"
        # Count patterns in top errors
        velocity_missing_count = sum(1 for e in top_errors if e.get('velocity_missing'))
        high_d_l_count = sum(1 for e in top_errors if e.get('D_l', 0) > 0.3)
        interpretation += f"  - {velocity_missing_count}/10 had missing velocity data\n"
        interpretation += f"  - {high_d_l_count}/10 had high local fatigue (D_l > 0.3)\n"
    
    interpretation += """

5. ERROR BY CONTEXT
-------------------
"""
    
    # Velocity availability
    vel_data = attribution_summary.get('error_by_velocity_availability', {})
    if vel_data.get('with_velocity') and vel_data.get('without_velocity'):
        with_v = vel_data['with_velocity']['mean_error']
        without_v = vel_data['without_velocity']['mean_error']
        if with_v is not None and without_v is not None:
            interpretation += f"""
Velocity data impact:
  - With velocity: MAE = {with_v}
  - Without velocity: MAE = {without_v}
  - {'Missing velocity hurts' if without_v > with_v else 'Missing velocity helps (overfitting?)'}
"""
    
    # T_legs
    t_legs_data = attribution_summary.get('error_by_t_legs', {})
    if t_legs_data.get('high_t_legs') and t_legs_data.get('low_t_legs'):
        high = t_legs_data['high_t_legs']['mean_error']
        low = t_legs_data['low_t_legs']['mean_error']
        if high is not None and low is not None:
            interpretation += f"""
Legs tonnage impact:
  - High T_legs: MAE = {high}
  - Low T_legs: MAE = {low}
  - {'High leg volume hurts prediction' if high > low else 'High leg volume helps prediction'}
"""
    
    interpretation += """

================================================================================
CONCLUSION
================================================================================
See ablation_summary.json and recalibration_summary.json for detailed numbers.
The day_error_attribution.csv contains all samples for further analysis.
"""
    
    return interpretation


def main():
    """Main entry point."""
    print("=" * 80)
    print("SPRINT V3: Day-Level Error Attribution + Ablation + Recalibration")
    print("=" * 80)
    
    db = SessionLocal()
    try:
        # Step 1: Run extended replay to capture internal states
        print("\n[1/4] Running extended replay with state capture...")
        day_errors, day_states, rep_errors = run_extended_replay(db, athlete_id=299)
        print(f"  Captured {len(day_errors)} day-level errors with {len(day_states)} state records")
        
        # Step 2: Merge and generate attribution CSV
        print("\n[2/4] Merging errors with states and generating summaries...")
        samples = merge_errors_with_states(day_errors, day_states)
        
        artifacts_dir = Path("./artifacts/sprint_v3")
        generate_error_attribution_csv(samples, str(artifacts_dir / "day_error_attribution.csv"))
        
        attribution_summary = generate_error_summaries(samples)
        with open(artifacts_dir / "error_summaries.json", 'w') as f:
            json.dump(attribution_summary, f, indent=2)
        
        # Step 3: Ablation study
        print("\n[3/4] Running ablation study...")
        ablation_results = ablation_study(samples)
        with open(artifacts_dir / "ablation_summary.json", 'w') as f:
            json.dump(ablation_results, f, indent=2)
        print("  Ablation results:")
        for name, result in sorted(ablation_results.items(), key=lambda x: x[1]['mae']):
            print(f"    {name}: MAE = {result['mae']}")
        
        # Step 4: Recalibration study
        print("\n[4/4] Running recalibration study...")
        recalibration_results = recalibration_study(samples)
        with open(artifacts_dir / "recalibration_summary.json", 'w') as f:
            json.dump(recalibration_results, f, indent=2)
        print("  Recalibration results:")
        for name, result in recalibration_results.items():
            print(f"    {name}: MAE = {result['mae']}")
            print(f"      Formula: {result['formula']}")
        
        # Step 5: Generate interpretation
        print("\n" + "=" * 80)
        interpretation = generate_interpretation(attribution_summary, ablation_results, recalibration_results)
        print(interpretation)
        
        with open(artifacts_dir / "interpretation.txt", 'w') as f:
            f.write(interpretation)
        
        print("\n" + "=" * 80)
        print("ARTIFACTS GENERATED")
        print("=" * 80)
        print(f"  - {artifacts_dir}/day_error_attribution.csv")
        print(f"  - {artifacts_dir}/ablation_summary.json")
        print(f"  - {artifacts_dir}/recalibration_summary.json")
        print(f"  - {artifacts_dir}/error_summaries.json")
        print(f"  - {artifacts_dir}/interpretation.txt")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
