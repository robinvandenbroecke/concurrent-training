"""
Sprint V4: Calibrate Observation Mapping and Rerun Evaluation

1. Load existing day_error data from Sprint V3
2. Calibrate constrained mapping parameters
3. Save calibrated parameters
4. Rerun replay/validate with new mapping
5. Compare old vs constrained MAE
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date
from pathlib import Path
import json
import csv
import statistics

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.eval.replay import ReplayRunner
from app.domain.observation_mapping import (
    calibrate_observation_mapping,
    ObservationMappingParams,
    save_mapping_params,
    predict_perf_y_constrained,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def load_day_error_data(csv_path: str) -> list:
    """Load day error data from CSV."""
    rows = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'date': row['date'],
                'lift': row['lift'],
                'D_l': float(row['D_l']),
                'D_sys': float(row['D_sys']),
                'T_legs': float(row['T_legs']),
                'observed': float(row['observed']),
                'predicted_legacy': float(row['predicted_model']),  # Old model used this
            })
    return rows


def compute_mae(predictions, observed):
    """Compute MAE."""
    return statistics.mean([abs(p - o) for p, o in zip(predictions, observed)])


def evaluate_mapping(day_errors, params, mapping_type="constrained"):
    """Evaluate a mapping configuration."""
    predictions = []
    observed_list = []
    
    for row in day_errors:
        if mapping_type == "constrained":
            pred = predict_perf_y_constrained(
                D_l=row['D_l'],
                D_sys=row['D_sys'],
                T_legs=row['T_legs'],
                params=params,
                lift=row['lift']
            )
        elif mapping_type == "legacy":
            # Legacy: readiness = 1 - D_l - 0.5*D_sys
            readiness = max(0, min(1, 1.0 - row['D_l'] - 0.5 * row['D_sys']))
            pred = 0.75 + 0.25 * readiness
            pred = max(0.60, min(1.10, pred))
        else:
            pred = row.get('predicted_legacy', 0.85)
        
        predictions.append(pred)
        observed_list.append(row['observed'])
    
    mae = compute_mae(predictions, observed_list)
    
    # Per-lift MAE
    per_lift_mae = {}
    lifts = list(set(row['lift'] for row in day_errors))
    for lift in lifts:
        lift_preds = [p for p, row in zip(predictions, day_errors) if row['lift'] == lift]
        lift_obs = [row['observed'] for row in day_errors if row['lift'] == lift]
        if lift_obs:
            per_lift_mae[lift] = round(compute_mae(lift_preds, lift_obs), 4)
    
    return {'mae': round(mae, 4), 'per_lift_mae': per_lift_mae}


def main():
    print("=" * 80)
    print("SPRINT V4: Calibrate Observation Mapping and Evaluate")
    print("=" * 80)
    
    # Step 1: Load existing day error data from Sprint V3
    print("\n[1/4] Loading day error data from Sprint V3...")
    day_errors_path = "./artifacts/sprint_v3/sprint_v3_run/day_errors.csv"
    
    # Also try to get state data from attribution CSV
    attribution_path = "./artifacts/sprint_v3/day_error_attribution.csv"
    
    day_errors = []
    if os.path.exists(attribution_path):
        with open(attribution_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                day_errors.append({
                    'date': row['date'],
                    'lift': row['lift'],
                    'D_l': float(row['D_l']),
                    'D_sys': float(row['D_sys']),
                    'T_legs': float(row['T_legs']),
                    'observed': float(row['observed']),
                    'predicted_legacy': float(row['predicted_model']),
                })
        print(f"  Loaded {len(day_errors)} samples from attribution CSV")
    else:
        print(f"  Warning: {attribution_path} not found")
        return
    
    # Step 2: Calibrate constrained mapping
    print("\n[2/4] Calibrating constrained mapping parameters...")
    
    # Use grid search with reasonable resolution
    calibration_result = calibrate_observation_mapping(
        day_errors,
        per_lift=False,
        grid_steps=8,
        refinement_steps=2
    )
    
    print(f"  Calibration completed in {calibration_result.iterations} iterations")
    print(f"  Calibrated parameters:")
    print(f"    a (intercept): {calibration_result.params.a:.4f}")
    print(f"    b_l (local): {calibration_result.params.b_l:.4f}")
    print(f"    b_sys (systemic): {calibration_result.params.b_sys:.4f}")
    print(f"    b_t (tissue): {calibration_result.params.b_t:.4f}")
    print(f"    Train MAE: {calibration_result.train_mae:.4f}")
    
    # Step 3: Save calibrated parameters
    print("\n[3/4] Saving calibrated parameters...")
    artifacts_dir = Path("./artifacts/synth_v2_run_v4")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    params_path = artifacts_dir / "calibrated_mapping_params.json"
    save_mapping_params(calibration_result.params, str(params_path))
    print(f"  Saved to: {params_path}")
    
    # Step 4: Evaluate and compare mappings
    print("\n[4/4] Evaluating mappings...")
    
    # Legacy mapping
    legacy_eval = evaluate_mapping(day_errors, None, mapping_type="legacy")
    
    # Default constrained mapping
    default_params = ObservationMappingParams.default_params()
    default_eval = evaluate_mapping(day_errors, default_params, mapping_type="constrained")
    
    # Calibrated constrained mapping
    calibrated_eval = evaluate_mapping(day_errors, calibration_result.params, mapping_type="constrained")
    
    # Compile results
    results = {
        'comparison': {
            'legacy_mapping': {
                'mae': legacy_eval['mae'],
                'description': 'Original hand-tuned readiness-based mapping',
            },
            'default_constrained': {
                'mae': default_eval['mae'],
                'description': 'Constrained mapping with default params',
                'params': default_params.to_dict(),
            },
            'calibrated_constrained': {
                'mae': calibrated_eval['mae'],
                'description': 'Constrained mapping with calibrated params',
                'params': calibration_result.params.to_dict(),
            },
        },
        'per_lift_mae': {
            'legacy': legacy_eval['per_lift_mae'],
            'default_constrained': default_eval['per_lift_mae'],
            'calibrated_constrained': calibrated_eval['per_lift_mae'],
        },
        'improvement': {
            'legacy_to_calibrated': round(legacy_eval['mae'] - calibrated_eval['mae'], 4),
            'legacy_to_calibrated_pct': round((legacy_eval['mae'] - calibrated_eval['mae']) / legacy_eval['mae'] * 100, 1),
        }
    }
    
    # Save results
    with open(artifacts_dir / "mapping_comparison.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"\nLegacy mapping MAE:           {legacy_eval['mae']:.4f}")
    print(f"Default constrained MAE:      {default_eval['mae']:.4f}")
    print(f"Calibrated constrained MAE:   {calibrated_eval['mae']:.4f}")
    print(f"\nImprovement (legacy → calibrated): {results['improvement']['legacy_to_calibrated']:.4f} "
          f"({results['improvement']['legacy_to_calibrated_pct']}% reduction)")
    
    print("\nPer-lift MAE (calibrated):")
    for lift, mae in sorted(calibrated_eval['per_lift_mae'].items()):
        print(f"  {lift}: {mae:.4f}")
    
    # Step 5: Rerun full replay with new mapping
    print("\n" + "=" * 80)
    print("RERUNNING FULL REPLAY WITH CONSTRAINED MAPPING")
    print("=" * 80)
    
    db = SessionLocal()
    try:
        runner = ReplayRunner(db, artifacts_dir=str(artifacts_dir))
        
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 31)
        
        report = runner.replay(
            athlete_id=299,
            date_from=date_from,
            date_to=date_to,
            dry_run=False
        )
        
        runner.write_artifacts("synth_v2_run_v4")
        
        print(f"\nReplay complete. Artifacts in: {artifacts_dir}")
        
        # Compute day-level MAE from replay output
        if runner.day_errors:
            legacy_errors = [abs(e['observed'] - e.get('predicted_legacy', e['predicted_model'])) 
                           for e in runner.day_errors if 'observed' in e]
            constrained_errors = [abs(e['observed'] - e.get('predicted_constrained', e['predicted_model'])) 
                                for e in runner.day_errors if 'observed' in e]
            
            if legacy_errors and constrained_errors:
                legacy_mae = statistics.mean(legacy_errors)
                constrained_mae = statistics.mean(constrained_errors)
                
                print(f"\nReplay Day-Level MAE:")
                print(f"  Legacy mapping:     {legacy_mae:.4f}")
                print(f"  Constrained mapping: {constrained_mae:.4f}")
                print(f"  Improvement:        {legacy_mae - constrained_mae:.4f} ({(legacy_mae - constrained_mae)/legacy_mae*100:.1f}%)")
        
    finally:
        db.close()
    
    print("\n" + "=" * 80)
    print("SPRINT V4 COMPLETE")
    print("=" * 80)
    print(f"\nArtifacts generated:")
    print(f"  - {artifacts_dir}/calibrated_mapping_params.json")
    print(f"  - {artifacts_dir}/mapping_comparison.json")
    print(f"  - {artifacts_dir}/synth_v2_run_v4/ (replay outputs)")


if __name__ == "__main__":
    main()
