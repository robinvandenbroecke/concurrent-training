"""
Sprint V2: Import and Validate Synthetic Dataset v2

Imports the realistic synthetic datasets and runs replay/validation.
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import statistics

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.adapters.strength_csv import import_strength_csv, parse_strength_csv
from app.adapters.endurance_csv import import_endurance_csv
from app.eval.replay import ReplayRunner
from app.eval.validation import ValidationReport


# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_athlete(db, athlete_id: int = 299):
    """Ensure athlete 299 exists with default profiles."""
    from app import models
    from app.services import AthleteService
    from app.types import LiftType
    
    athlete = db.query(models.Athlete).filter(models.Athlete.id == athlete_id).first()
    if not athlete:
        print(f"Creating athlete {athlete_id}...")
        athlete = models.Athlete(id=athlete_id, name=f"Synthetic Athlete {athlete_id}")
        db.add(athlete)
        db.commit()
    
    # Ensure lift profiles exist
    for lift in LiftType:
        if lift == LiftType.OTHER:
            continue
        profile = db.query(models.LiftProfile).filter(
            models.LiftProfile.athlete_id == athlete_id,
            models.LiftProfile.lift == lift
        ).first()
        if not profile:
            # Default profile values
            defaults = {
                LiftType.SQUAT: (0.55, 0.0032),
                LiftType.BENCH: (0.60, 0.0028),
                LiftType.DEADLIFT: (0.50, 0.0030),
                LiftType.PRESS: (0.58, 0.0025),
                LiftType.POWER_CLEAN: (0.75, 0.0040),
                LiftType.CLEAN: (0.75, 0.0040),
            }
            a, b = defaults.get(lift, (0.55, 0.0030))
            profile = models.LiftProfile(
                athlete_id=athlete_id,
                lift=lift,
                a=a,
                b=b
            )
            db.add(profile)
    
    db.commit()
    print(f"Athlete {athlete_id} ready with profiles.")


def import_datasets(db, athlete_id: int = 299):
    """Import both synthetic datasets."""
    print("\n" + "=" * 60)
    print("IMPORTING SYNTHETIC DATASETS V2")
    print("=" * 60)
    
    # Import strength
    strength_path = "/mnt/data/strength_log_vbt_synthetic_v2.csv"
    print(f"\nImporting strength data from: {strength_path}")
    
    # First parse to get stats
    parsed_sessions = parse_strength_csv(strength_path)
    print(f"  Parsed {len(parsed_sessions)} sessions")
    
    # Then import
    result = import_strength_csv(db, athlete_id, strength_path, dry_run=False)
    print(f"  Created: {result.sessions_created} sessions")
    print(f"  Skipped: {result.sessions_skipped} sessions")
    print(f"  Total sets: {result.sets_total}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for e in result.errors[:3]:
            print(f"    - {e}")
    
    # Import endurance
    endurance_path = "/mnt/data/endurance_log_synthetic_v2.csv"
    print(f"\nImporting endurance data from: {endurance_path}")
    
    result = import_endurance_csv(db, athlete_id, endurance_path, dry_run=False)
    print(f"  Created: {result.sessions_created} sessions")
    print(f"  Skipped: {result.sessions_skipped} sessions")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for e in result.errors[:3]:
            print(f"    - {e}")
    
    return True


def run_replay_validation(db, athlete_id: int = 299):
    """Run replay and validation on the imported data."""
    print("\n" + "=" * 60)
    print("REPLAY & VALIDATION")
    print("=" * 60)
    
    runner = ReplayRunner(db, artifacts_dir="./artifacts/synthetic_v2")
    
    # Run replay for full date range (12 weeks from Jan 1, 2026)
    date_from = date(2026, 1, 1)
    date_to = date(2026, 3, 31)
    
    print(f"\nReplaying athlete {athlete_id} from {date_from} to {date_to}...")
    
    report = runner.replay(
        athlete_id=athlete_id,
        date_from=date_from,
        date_to=date_to,
        dry_run=False
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("REPLAY SUMMARY")
    print("=" * 60)
    
    if hasattr(report, 'strength_rep'):
        print(f"\nStrength Rep-Level Metrics:")
        print(f"  RMSE: {report.strength_rep.get('rmse', 'N/A')}")
        print(f"  MAE: {report.strength_rep.get('mae', 'N/A')}")
        print(f"  R²: {report.strength_rep.get('r2', 'N/A')}")
    
    if hasattr(report, 'strength_day'):
        print(f"\nStrength Day-Level Metrics:")
        print(f"  RMSE: {report.strength_day.get('rmse', 'N/A')}")
        print(f"  MAE: {report.strength_day.get('mae', 'N/A')}")
    
    if hasattr(report, 'trend_metrics'):
        print(f"\nTrend Classification:")
        print(f"  Accuracy: {report.trend_metrics.get('accuracy', 'N/A')}")
        print(f"  Precision: {report.trend_metrics.get('precision', 'N/A')}")
    
    if hasattr(report, 'endurance_metrics'):
        print(f"\nEndurance Metrics:")
        print(f"  Accuracy: {report.endurance_metrics.get('accuracy', 'N/A')}")
    
    return report


def generate_v2_summary_report():
    """Generate a summary report comparing v2 to v1 assumptions."""
    print("\n" + "=" * 60)
    print("SYNTHETIC V2 DATASET SUMMARY REPORT")
    print("=" * 60)
    
    report = []
    report.append("SYNTHETIC DATASET V2 - REALISM IMPROVEMENTS")
    report.append("=" * 60)
    report.append("")
    
    # Dataset characteristics
    report.append("DATASET CHARACTERISTICS:")
    report.append("-" * 40)
    report.append("Strength Dataset:")
    report.append("  - Duration: 12 weeks")
    report.append("  - Frequency: 3 sessions/week")
    report.append("  - Lifts: squat, bench, deadlift, press, power_clean")
    report.append("  - Session types: strength, volume, power/technique")
    report.append("  - Periodization: 3:1 load/deload tendency (not rigid)")
    report.append("")
    
    report.append("Endurance Dataset:")
    report.append("  - Duration: 12 weeks")
    report.append("  - Frequency: 4 sessions/week average")
    report.append("  - Sports: cycling (50%), running (35%), swimming (15%)")
    report.append("  - Types: Z2, tempo, HIIT, long sessions")
    report.append("")
    
    # Realism features
    report.append("REALISM FEATURES (V2 vs V1):")
    report.append("-" * 40)
    report.append("")
    
    report.append("1. NONLINEAR LOAD-VELOCITY BEHAVIOR:")
    report.append("   V1: Perfectly linear v_ref = a - b*load")
    report.append("   V2: Piecewise with curvature:")
    report.append("       - Linear in mid-range (40-85% 1RM)")
    report.append("       - Faster drop-off near high intensity (>85%)")
    report.append("       - Flatter curve at low intensity (<40%)")
    report.append("")
    
    report.append("2. WITHIN-SET BEHAVIOR:")
    report.append("   V1: Perfect exponential decay")
    report.append("   V2: Realistic variability:")
    report.append("       - Occasional early potentiation (5% of sets)")
    report.append("       - Technical noise (bar-path variability)")
    report.append("       - Catastrophe near failure (VL > 0.30)")
    report.append("       - Lift-specific decay rates")
    report.append("")
    
    report.append("3. DAY-TO-DAY READINESS:")
    report.append("   V1: Perfect consistency")
    report.append("   V2: Realistic variation:")
    report.append("       - 15% global bad days (readiness 0.88-0.96)")
    report.append("       - 10% great days (readiness 1.03-1.08)")
    report.append("       - 20% lift-specific deviations")
    report.append("       - Asymmetry across lifts (e.g., deadlift down, bench normal)")
    report.append("")
    
    report.append("4. MISSINGNESS / IMPERFECT LOGGING:")
    report.append("   V1: Complete data")
    report.append("   V2: Realistic missingness:")
    report.append("       - 25% of sets missing velocity data")
    report.append("       - 10% missing rest_sec")
    report.append("       - Some RPE missing")
    report.append("")
    
    report.append("5. TECHNICAL NOISE:")
    report.append("   V1: None")
    report.append("   V2: Lift-specific technical noise:")
    report.append("       - Squat/deadlift: σ=0.08 (higher)")
    report.append("       - Bench: σ=0.04 (lower)")
    report.append("       - Power clean: σ=0.10 (highest)")
    report.append("")
    
    report.append("6. BREAKTHROUGH OPPORTUNITIES:")
    report.append("   V1: None")
    report.append("   V2: 5% breakthrough sessions:")
    report.append("       - 8% better performance")
    report.append("       - Can trigger provisional/confirmed breakthroughs")
    report.append("")
    
    report.append("7. PLAUSIBLE LOADS/REPS:")
    report.append("   V1: Could have unrealistic combinations")
    report.append("   V2: Amateur-intermediate/advanced ranges only")
    report.append("       - Loads within realistic 1RM percentages")
    report.append("       - Reps appropriate for intensity")
    report.append("")
    
    # Statistical summary
    report.append("STATISTICAL SUMMARY:")
    report.append("-" * 40)
    
    # Parse and analyze strength data
    import csv
    import json
    
    # Strength stats
    with open("/mnt/data/strength_log_vbt_synthetic_v2.csv", 'r') as f:
        reader = csv.DictReader(f)
        strength_rows = list(reader)
    
    total_sets = len(strength_rows)
    sets_with_velocity = sum(1 for r in strength_rows if r.get('velocities') and r['velocities'].strip())
    missing_velocity = total_sets - sets_with_velocity
    
    loads = [float(r['load_kg']) for r in strength_rows]
    reps = [int(r['reps']) for r in strength_rows]
    
    report.append(f"Strength Data:")
    report.append(f"  Total sets: {total_sets}")
    report.append(f"  Sets with velocity: {sets_with_velocity} ({100*sets_with_velocity/total_sets:.1f}%)")
    report.append(f"  Missing velocity: {missing_velocity} ({100*missing_velocity/total_sets:.1f}%)")
    report.append(f"  Load range: {min(loads):.1f} - {max(loads):.1f} kg")
    report.append(f"  Avg load: {statistics.mean(loads):.1f} kg")
    report.append(f"  Reps range: {min(reps)} - {max(reps)}")
    report.append(f"  Avg reps: {statistics.mean(reps):.1f}")
    report.append("")
    
    # Endurance stats
    with open("/mnt/data/endurance_log_synthetic_v2.csv", 'r') as f:
        reader = csv.DictReader(f)
        endurance_rows = list(reader)
    
    sports = {}
    for r in endurance_rows:
        s = r['sport']
        sports[s] = sports.get(s, 0) + 1
    
    durations = [int(r['duration_min']) for r in endurance_rows]
    tss_values = [float(r['tss']) for r in endurance_rows]
    
    report.append(f"Endurance Data:")
    report.append(f"  Total sessions: {len(endurance_rows)}")
    report.append(f"  Cycling: {sports.get('cycling', 0)} ({100*sports.get('cycling',0)/len(endurance_rows):.0f}%)")
    report.append(f"  Running: {sports.get('running', 0)} ({100*sports.get('running',0)/len(endurance_rows):.0f}%)")
    report.append(f"  Swimming: {sports.get('swimming', 0)} ({100*sports.get('swimming',0)/len(endurance_rows):.0f}%)")
    report.append(f"  Duration range: {min(durations)} - {max(durations)} min")
    report.append(f"  Avg duration: {statistics.mean(durations):.0f} min")
    report.append(f"  TSS range: {min(tss_values):.1f} - {max(tss_values):.1f}")
    report.append(f"  Avg TSS: {statistics.mean(tss_values):.1f}")
    report.append("")
    
    # Model stress factors
    report.append("MODEL STRESS FACTORS:")
    report.append("-" * 40)
    report.append("V2 dataset intentionally stress-tests:")
    report.append("  ✓ rep_engine: Nonlinear L-V, noisy data, missing values")
    report.append("  ✓ day_engine: Variable readiness, cross-domain fatigue")
    report.append("  ✓ capacity_profile: Breakthrough detection with noise")
    report.append("  ✓ coach/program: Decisions under uncertainty")
    report.append("")
    
    # Write report
    report_text = "\n".join(report)
    print(report_text)
    
    report_path = "/mnt/data/synthetic_v2_summary_report.txt"
    with open(report_path, 'w') as f:
        f.write(report_text)
    
    print(f"\nReport saved to: {report_path}")
    
    return report_text


def main():
    """Main entry point."""
    print("=" * 60)
    print("SYNTHETIC DATASET V2 - IMPORT & VALIDATION")
    print("=" * 60)
    
    # Create database tables if needed
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Setup athlete
        setup_athlete(db, athlete_id=299)
        
        # Import datasets
        import_datasets(db, athlete_id=299)
        
        # Run replay validation
        report = run_replay_validation(db, athlete_id=299)
        
        # Generate summary report
        summary = generate_v2_summary_report()
        
        print("\n" + "=" * 60)
        print("COMPLETE!")
        print("=" * 60)
        print("\nArtifacts generated:")
        print("  1. /mnt/data/strength_log_vbt_synthetic_v2.csv")
        print("  2. /mnt/data/endurance_log_synthetic_v2.csv")
        print("  3. /mnt/data/synthetic_v2_summary_report.txt")
        print("  4. ./artifacts/synthetic_v2/ (replay outputs)")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
