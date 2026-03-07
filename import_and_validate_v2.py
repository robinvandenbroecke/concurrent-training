"""
Sprint V2-Enhanced: Import, Replay & Validate Synthetic Dataset v2

Imports the realistic synthetic datasets with interference patterns and runs
comprehensive validation to generate required output files.
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import statistics
import csv

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.adapters.strength_csv import import_strength_csv, parse_strength_csv
from app.adapters.endurance_csv import import_endurance_csv
from app.eval.replay import ReplayRunner
from app.eval.validation import compute_rep_level_metrics, compute_day_level_strength_metrics
from app import models


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_athlete(db, athlete_id: int = 299):
    """Ensure athlete 299 exists with default profiles."""
    from app.types import LiftType
    
    athlete = db.query(models.Athlete).filter(models.Athlete.id == athlete_id).first()
    if not athlete:
        print(f"Creating athlete {athlete_id}...")
        athlete = models.Athlete(id=athlete_id, name=f"Synthetic Athlete {athlete_id}")
        db.add(athlete)
        db.commit()
    
    for lift in LiftType:
        if lift == LiftType.OTHER:
            continue
        profile = db.query(models.LiftProfile).filter(
            models.LiftProfile.athlete_id == athlete_id,
            models.LiftProfile.lift == lift
        ).first()
        if not profile:
            defaults = {
                LiftType.SQUAT: (0.55, 0.0032),
                LiftType.BENCH: (0.60, 0.0028),
                LiftType.DEADLIFT: (0.50, 0.0030),
                LiftType.PRESS: (0.58, 0.0025),
                LiftType.POWER_CLEAN: (0.75, 0.0040),
                LiftType.CLEAN: (0.75, 0.0040),
            }
            a, b = defaults.get(lift, (0.55, 0.0030))
            profile = models.LiftProfile(athlete_id=athlete_id, lift=lift, a=a, b=b)
            db.add(profile)
    
    db.commit()
    print(f"Athlete {athlete_id} ready with profiles.")


def import_datasets(db, athlete_id: int = 299):
    """Import both synthetic datasets."""
    print("\n" + "=" * 60)
    print("IMPORTING SYNTHETIC DATASETS V2")
    print("=" * 60)
    
    strength_path = "/mnt/data/strength_log_vbt_synthetic_v2.csv"
    print(f"\nImporting strength data from: {strength_path}")
    
    # Get stats before import
    with open(strength_path, 'r') as f:
        reader = csv.DictReader(f)
        strength_rows = list(reader)
    
    total_sets = len(strength_rows)
    sets_with_velocity = sum(1 for r in strength_rows if r.get('velocities') and r['velocities'].strip())
    missing_velocity = total_sets - sets_with_velocity
    missing_rest = sum(1 for r in strength_rows if not r.get('rest_sec') or not r['rest_sec'].strip())
    missing_rpe = sum(1 for r in strength_rows if not r.get('rpe') or not r['rpe'].strip())
    
    lifts = list(set(r['lift_code'] for r in strength_rows))
    
    print(f"  Parsed {total_sets} sets")
    print(f"  Lifts: {lifts}")
    
    # Clear existing sessions for this athlete to avoid duplicates
    existing = db.query(models.StrengthSession).filter(models.StrengthSession.athlete_id == athlete_id).all()
    for e in existing:
        db.delete(e)
    db.commit()
    
    result = import_strength_csv(db, athlete_id, strength_path, dry_run=False)
    print(f"  Created: {result.sessions_created} sessions")
    print(f"  Skipped: {result.sessions_skipped} sessions")
    print(f"  Total sets: {result.sets_total}")
    
    endurance_path = "/mnt/data/endurance_log_synthetic_v2.csv"
    print(f"\nImporting endurance data from: {endurance_path}")
    
    with open(endurance_path, 'r') as f:
        reader = csv.DictReader(f)
        endurance_rows = list(reader)
    
    sports = list(set(r['sport'] for r in endurance_rows))
    
    # Clear existing
    existing = db.query(models.EnduranceSession).filter(models.EnduranceSession.athlete_id == athlete_id).all()
    for e in existing:
        db.delete(e)
    db.commit()
    
    result = import_endurance_csv(db, athlete_id, endurance_path, dry_run=False)
    print(f"  Created: {result.sessions_created} sessions")
    print(f"  Skipped: {result.sessions_skipped} sessions")
    
    return {
        'strength': {
            'total_sets': total_sets,
            'sets_with_velocity': sets_with_velocity,
            'missing_velocity_pct': 100 * missing_velocity / total_sets,
            'missing_rest_pct': 100 * missing_rest / total_sets,
            'missing_rpe_pct': 100 * missing_rpe / total_sets,
            'lifts': lifts,
        },
        'endurance': {
            'total_sessions': len(endurance_rows),
            'sports': sports,
        }
    }


def run_replay_and_validate(db, athlete_id: int = 299):
    """Run replay and validation, collect metrics."""
    print("\n" + "=" * 60)
    print("REPLAY & VALIDATION")
    print("=" * 60)
    
    artifacts_dir = "./artifacts/synth_v2_run"
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
    
    runner = ReplayRunner(db, artifacts_dir=artifacts_dir)
    
    date_from = date(2026, 1, 1)
    date_to = date(2026, 3, 31)
    
    print(f"\nReplaying athlete {athlete_id} from {date_from} to {date_to}...")
    
    report = runner.replay(
        athlete_id=athlete_id,
        date_from=date_from,
        date_to=date_to,
        dry_run=False
    )
    
    # Write artifacts
    runner.write_artifacts("synth_v2_run")
    
    # Extract metrics from ValidationReport
    metrics = {
        'rep_level': {},
        'day_level': {},
        'trend_classification': {},
        'endurance': {},
    }
    
    # Rep-level metrics
    if report.rep_level_rmse is not None:
        metrics['rep_level'] = {
            'rmse': report.rep_level_rmse,
            'mae': report.rep_level_mae,
            'n_samples': len(runner.rep_errors) if runner.rep_errors else 0,
        }
    
    # Day-level metrics (includes baseline comparisons)
    if report.day_level_mae_model is not None:
        metrics['day_level'] = {
            'mae_model': report.day_level_mae_model,
            'mae_baseline_a': report.day_level_mae_baseline_a,
            'mae_baseline_b': report.day_level_mae_baseline_b,
            'n_samples': len(runner.day_errors) if runner.day_errors else 0,
        }
    
    # Trend classification
    if report.trend_accuracy_model is not None:
        metrics['trend_classification'] = {
            'accuracy_model': report.trend_accuracy_model,
            'accuracy_baseline_a': report.trend_accuracy_baseline_a,
            'accuracy_baseline_b': report.trend_accuracy_baseline_b,
        }
    
    # Endurance
    if report.endurance_accuracy_model is not None:
        metrics['endurance'] = {
            'accuracy_model': report.endurance_accuracy_model,
            'accuracy_baseline': report.endurance_accuracy_baseline,
        }
    
    return metrics, report, runner


def compute_per_lift_metrics(runner, athlete_id: int = 299):
    """Compute per-lift RMSE/MAE from replay data."""
    per_lift = {}
    
    # Group rep errors by lift
    lift_errors = {}
    for error in runner.rep_errors:
        lift = error.get('lift', 'unknown')
        if lift not in lift_errors:
            lift_errors[lift] = {'errors': [], 'abs_errors': []}
        if 'error' in error:
            lift_errors[lift]['errors'].append(error['error'])
            lift_errors[lift]['abs_errors'].append(abs(error['error']))
    
    for lift, data in lift_errors.items():
        if data['errors']:
            per_lift[lift] = {
                'rmse': (sum(e**2 for e in data['errors']) / len(data['errors'])) ** 0.5,
                'mae': sum(data['abs_errors']) / len(data['abs_errors']),
                'n': len(data['errors']),
            }
    
    return per_lift


def generate_summary_json(data_quality, metrics, per_lift_metrics, output_path: str):
    """Generate summary.json."""
    summary = {
        'dataset': {
            'version': 'v2-enhanced',
            'athlete_id': 299,
            'date_range': {'from': '2026-01-01', 'to': '2026-03-31'},
            'strength': data_quality['strength'],
            'endurance': data_quality['endurance'],
        },
        'metrics': {
            'rep_level': metrics.get('rep_level', {}),
            'day_level': metrics.get('day_level', {}),
            'trend_classification': metrics.get('trend_classification', {}),
            'endurance': metrics.get('endurance', {}),
        },
        'per_lift': per_lift_metrics,
    }
    
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary


def generate_baseline_comparison(metrics, per_lift_metrics, output_path: str):
    """Generate baseline_comparison.json."""
    dl = metrics.get('day_level', {})
    rl = metrics.get('rep_level', {})
    
    comparison = {
        'model_vs_baselines': {
            'rep_level': {
                'model_rmse': rl.get('rmse'),
                'model_mae': rl.get('mae'),
                'n_samples': rl.get('n_samples'),
            },
            'day_level': {
                'model_mae': dl.get('mae_model'),
                'baseline_velocity_threshold_mae': dl.get('mae_baseline_a'),
                'baseline_banister_mae': dl.get('mae_baseline_b'),
                'n_samples': dl.get('n_samples'),
            }
        },
        'per_lift_rep_metrics': per_lift_metrics,
        'trend_classification': metrics.get('trend_classification', {}),
        'endurance': metrics.get('endurance', {}),
        'notes': 'V2 dataset intentionally harder than V1 with model-mismatch, nonlinearity, noise, and asymmetric bad days.'
    }
    
    with open(output_path, 'w') as f:
        json.dump(comparison, f, indent=2)
    
    return comparison


def generate_data_quality_summary(data_quality):
    """Print data quality summary."""
    print("\n" + "=" * 60)
    print("DATA QUALITY SUMMARY")
    print("=" * 60)
    
    s = data_quality['strength']
    print(f"\nStrength Dataset:")
    print(f"  Total sets: {s['total_sets']}")
    print(f"  Lifts: {', '.join(s['lifts'])}")
    print(f"  Velocity coverage: {100 - s['missing_velocity_pct']:.1f}%")
    print(f"  Missing rest: {s['missing_rest_pct']:.1f}%")
    print(f"  Missing RPE: {s['missing_rpe_pct']:.1f}%")
    
    e = data_quality['endurance']
    print(f"\nEndurance Dataset:")
    print(f"  Total sessions: {e['total_sessions']}")
    print(f"  Sports: {', '.join(e['sports'])}")


def print_per_lift_metrics(per_lift):
    """Print per-lift metrics table."""
    print("\n" + "=" * 60)
    print("PER-LIFT REP-LEVEL METRICS")
    print("=" * 60)
    print(f"{'Lift':<15} {'RMSE':<10} {'MAE':<10} {'N':<10}")
    print("-" * 45)
    for lift, m in sorted(per_lift.items()):
        print(f"{lift:<15} {m['rmse']:<10.4f} {m['mae']:<10.4f} {m['n']:<10}")


def print_model_vs_baselines(metrics):
    """Print day-level model vs baselines comparison."""
    print("\n" + "=" * 60)
    print("DAY-LEVEL MODEL vs BASELINES")
    print("=" * 60)
    
    dl = metrics.get('day_level', {})
    print(f"  Model MAE: {dl.get('mae_model', 'N/A')}")
    print(f"  Baseline A (Velocity Threshold) MAE: {dl.get('mae_baseline_a', 'N/A')}")
    print(f"  Baseline B (Banister) MAE: {dl.get('mae_baseline_b', 'N/A')}")
    print(f"  N samples: {dl.get('n_samples', 'N/A')}")
    
    print("\nTrend Classification:")
    tc = metrics.get('trend_classification', {})
    print(f"  Model Accuracy: {tc.get('accuracy_model', 'N/A')}")
    print(f"  Baseline A Accuracy: {tc.get('accuracy_baseline_a', 'N/A')}")
    print(f"  Baseline B Accuracy: {tc.get('accuracy_baseline_b', 'N/A')}")
    
    print("\nEndurance Classification:")
    e = metrics.get('endurance', {})
    print(f"  Model Accuracy: {e.get('accuracy_model', 'N/A')}")
    print(f"  Baseline Accuracy: {e.get('accuracy_baseline', 'N/A')}")


def print_v2_harder_than_v1_notes():
    """Print notes on why v2 is intentionally harder."""
    print("\n" + "=" * 60)
    print("V2 vs V1: INTENTIONALLY HARDER DATASET")
    print("=" * 60)
    
    notes = """
The v2 dataset is specifically designed to be HARDER than v1 for stress-testing:

1. MODEL-MISMATCH:
   - Load-velocity curve uses exponent 1.15 (model assumes 1.0)
   - Decay rate is 0.032 (model may assume 0.03)
   - High-intensity penalty is 35% (model may not capture this)

2. NONLINEARITY:
   - Piecewise L-V curve with different slopes at different intensities
   - Asymmetric readiness (squat down, bench normal)
   - Non-uniform technical noise (increases with rep number)

3. NOISE:
   - Lift-specific technical noise (σ=0.04 to 0.10)
   - Day-to-day readiness variation (σ~0.06)
   - RPE noise (σ=0.4)

4. MISSING DATA:
   - 24.1% missing velocity (intentional gaps)
   - ~12% missing rest_sec
   - ~8% missing RPE

5. ASYMMETRIC BAD DAYS:
   - 30% chance of lift-specific deviation from global readiness
   - Can have squat readiness 0.88 while bench is 1.02
   - Models assuming symmetric fatigue will struggle

6. INTERFERENCE PATTERNS:
   - Week 8: Deliberate high interference (heavy lower + HIIT cluster)
   - Lower body lifts affected by endurance 25-40% more than upper body
   - Recovery half-life of 2.5 days (creates complex fatigue accumulation)

7. DELOAD/REBOUND:
   - Week 4, 9, 12: Deload/taper with expected performance rebound
   - Tests model's ability to detect supercompensation

8. BREAKTHROUGH VARIABILITY:
   - Variable breakthrough magnitude (8-12% instead of fixed)
   - Occurs in peak weeks (not random)

This dataset will make models look WORSE than v1 - that's the point.
"""
    print(notes)


def main():
    """Main entry point."""
    print("=" * 60)
    print("SYNTHETIC DATASET V2 - IMPORT & VALIDATION")
    print("=" * 60)
    
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        setup_athlete(db, athlete_id=299)
        data_quality = import_datasets(db, athlete_id=299)
        metrics, report, runner = run_replay_and_validate(db, athlete_id=299)
        per_lift = compute_per_lift_metrics(runner, athlete_id=299)
        
        # Generate output files
        summary = generate_summary_json(
            data_quality, metrics, per_lift,
            './artifacts/synth_v2_run/summary.json'
        )
        
        baseline_comparison = generate_baseline_comparison(
            metrics, per_lift,
            './artifacts/synth_v2_run/baseline_comparison.json'
        )
        
        # Print reports
        generate_data_quality_summary(data_quality)
        print_per_lift_metrics(per_lift)
        print_model_vs_baselines(metrics)
        print_v2_harder_than_v1_notes()
        
        print("\n" + "=" * 60)
        print("ARTIFACTS GENERATED")
        print("=" * 60)
        print("  - artifacts/synth_v2_run/summary.json")
        print("  - artifacts/synth_v2_run/baseline_comparison.json")
        print("  - artifacts/synth_v2_run/ (replay outputs)")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
