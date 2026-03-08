"""
Sprint V4.3: Fix Observation Diagnostics for Trustworthiness

Addresses V4.2 issues:
1. Target-scale mismatch: observed_perf_y mean ~1.84 vs mapping bounds [0.60, 1.10]
2. Ablation logic bug: masking not properly enforced during calibration
3. Diagnostic interpretation logic errors

Steps:
1. Trace and document observed_perf_y construction
2. Add target-scale consistency checks with clipping analysis
3. Fix ablation logic to properly enforce feature masking
4. Rerun diagnostics with corrected tooling
5. Produce trustworthy recommendation
"""
import sys
import os
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from datetime import date
from pathlib import Path
import json
import csv
import statistics
import math
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.eval.replay import ReplayRunner
from app.domain.observation_mapping import (
    calibrate_observation_mapping,
    ObservationMappingParams,
    predict_perf_y_constrained,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concurrent_training.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def compute_mae(predictions, observed):
    """Compute MAE."""
    return statistics.mean([abs(p - o) for p, o in zip(predictions, observed)])


def pearson_correlation(x, y):
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return numerator / (denom_x * denom_y)


def compute_descriptive_stats(values):
    """Compute descriptive statistics."""
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    def percentile(p):
        idx = int(p / 100.0 * (n - 1))
        return sorted_vals[max(0, min(n - 1, idx))]
    mean_val = statistics.mean(sorted_vals)
    std_val = statistics.stdev(sorted_vals) if n > 1 else 0.0
    return {
        'mean': round(mean_val, 6),
        'std': round(std_val, 6),
        'min': round(min(sorted_vals), 6),
        'max': round(max(sorted_vals), 6),
        'p10': round(percentile(10), 6),
        'p50': round(percentile(50), 6),
        'p90': round(percentile(90), 6),
        'n': n,
    }


# =============================================================================
# STEP 1: TRACE OBSERVED TARGET CONSTRUCTION
# =============================================================================

def trace_target_construction(rows):
    """
    Document how observed_perf_y is constructed.
    
    From code inspection of replay.py _extract_observed_perf_y:
    - Source: v_obs_list[1] / v_obs_list[0] (velocity ratio rep2/rep1)
    - Formula: perf_y = velocity_rep2 / velocity_rep1
    - Expected range: ~0.5 to ~1.2 (velocity typically drops between reps)
    """
    print("=" * 80)
    print("STEP 1: Trace Observed Target Construction")
    print("=" * 80)
    
    observed_values = [r['observed_perf_y'] for r in rows]
    stats = compute_descriptive_stats(observed_values)
    
    target_def = {
        'code_path': 'app/eval/replay.py::_extract_observed_perf_y',
        'formula': 'perf_y = velocity_rep2 / velocity_rep1',
        'description': 'Ratio of observed velocity at rep 2 to rep 1. Represents performance degradation between first two reps.',
        'expected_range': {
            'min': 0.5,
            'max': 1.2,
            'description': 'Velocity typically drops 0-50% between reps, so ratio should be 0.5-1.0, occasionally slightly above 1.0 if athlete warms up into the set.'
        },
        'actual_observed_range': {
            'min': stats['min'],
            'max': stats['max'],
            'mean': stats['mean'],
            'std': stats['std'],
            'p10': stats['p10'],
            'p50': stats['p50'],
            'p90': stats['p90'],
        },
        'scale_mismatch_warning': stats['mean'] > 1.5 or stats['max'] > 2.0,
    }
    
    print(f"\nTarget Definition:")
    print(f"  Path: {target_def['code_path']}")
    print(f"  Formula: {target_def['formula']}")
    print(f"  Description: {target_def['description']}")
    
    print(f"\nExpected Range: [{target_def['expected_range']['min']}, {target_def['expected_range']['max']}]")
    print(f"Actual Range: [{stats['min']:.4f}, {stats['max']:.4f}]")
    print(f"Actual Mean: {stats['mean']:.4f}")
    
    if target_def['scale_mismatch_warning']:
        print("\n  ⚠⚠⚠ CRITICAL SCALE MISMATCH ⚠⚠⚠")
        print(f"  Observed target mean ({stats['mean']:.2f}) is FAR outside expected range!")
        print("  The constrained mapping bounds [0.60, 1.10] are incompatible with this target.")
        print("  Clipping will dominate MAE.")
    
    return target_def


# =============================================================================
# STEP 2: TARGET-SCALE CONSISTENCY CHECKS
# =============================================================================

def analyze_target_scale_consistency(rows):
    """
    Analyze target-scale consistency with clipping diagnostics.
    
    For each sample, compute:
    - raw predicted value (unclamped)
    - clamped predicted value
    - clipping indicators
    """
    print("\n" + "=" * 80)
    print("STEP 2: Target-Scale Consistency Checks")
    print("=" * 80)
    
    y_min, y_max = 0.60, 1.10  # Constrained mapping bounds
    
    # Use default params to compute predictions
    default_params = ObservationMappingParams.default_params()
    
    unclamped_preds = []
    clamped_preds = []
    observed = []
    lower_clipped = []
    upper_clipped = []
    
    for row in rows:
        # Compute unclamped prediction
        D_l, D_sys, T_legs = row['D_l'], row['D_sys'], row['T_legs']
        
        # Manual unclamped calculation
        fatigue_terms = (
            default_params.b_l * max(0.0, 1.0 - D_l) +
            default_params.b_sys * max(0.0, 1.0 - D_sys) +
            default_params.b_t * max(0.0, 1.0 - T_legs)
        )
        unclamped = default_params.a + fatigue_terms
        
        # Clamped prediction
        clamped = predict_perf_y_constrained(D_l, D_sys, T_legs, default_params, row['lift'])
        
        unclamped_preds.append(unclamped)
        clamped_preds.append(clamped)
        observed.append(row['observed_perf_y'])
        lower_clipped.append(clamped <= y_min + 0.001)
        upper_clipped.append(clamped >= y_max - 0.001)
    
    # Compute statistics
    n_lower = sum(lower_clipped)
    n_upper = sum(upper_clipped)
    n_total = len(rows)
    
    diagnostics = {
        'constrained_mapping_bounds': {'y_min': y_min, 'y_max': y_max},
        'clipping_frequency': {
            'lower_bound': {'count': n_lower, 'fraction': round(n_lower / n_total, 4)},
            'upper_bound': {'count': n_upper, 'fraction': round(n_upper / n_total, 4)},
            'total_clipped': {'count': n_lower + n_upper, 'fraction': round((n_lower + n_upper) / n_total, 4)},
        },
        'observed_target_distribution': compute_descriptive_stats(observed),
        'predicted_unclamped_distribution': compute_descriptive_stats(unclamped_preds),
        'predicted_clamped_distribution': compute_descriptive_stats(clamped_preds),
        'mae_comparisons': {
            'unclamped_vs_observed': round(compute_mae(unclamped_preds, observed), 4),
            'clamped_vs_observed': round(compute_mae(clamped_preds, observed), 4),
        },
        'scale_compatibility_assessment': {
            'observed_mean_in_bounds': y_min <= statistics.mean(observed) <= y_max,
            'observed_range_fits_bounds': min(observed) >= y_min and max(observed) <= y_max,
            'clipping_dominates': (n_lower + n_upper) / n_total > 0.5,
        }
    }
    
    print(f"\nClipping Analysis (with default params):")
    print(f"  Lower bound clips: {n_lower}/{n_total} ({n_lower/n_total*100:.1f}%)")
    print(f"  Upper bound clips: {n_upper}/{n_total} ({n_upper/n_total*100:.1f}%)")
    print(f"  Total clipped: {n_lower + n_upper}/{n_total} ({(n_lower+n_upper)/n_total*100:.1f}%)")
    
    print(f"\nDistribution Comparison:")
    print(f"  Observed:     mean={diagnostics['observed_target_distribution']['mean']:.4f}, "
          f"range=[{diagnostics['observed_target_distribution']['min']:.4f}, {diagnostics['observed_target_distribution']['max']:.4f}]")
    print(f"  Unclamped:    mean={diagnostics['predicted_unclamped_distribution']['mean']:.4f}, "
          f"range=[{diagnostics['predicted_unclamped_distribution']['min']:.4f}, {diagnostics['predicted_unclamped_distribution']['max']:.4f}]")
    print(f"  Clamped:      mean={diagnostics['predicted_clamped_distribution']['mean']:.4f}, "
          f"range=[{diagnostics['predicted_clamped_distribution']['min']:.4f}, {diagnostics['predicted_clamped_distribution']['max']:.4f}]")
    
    print(f"\nMAE (with default params):")
    print(f"  Unclamped vs Observed: {diagnostics['mae_comparisons']['unclamped_vs_observed']:.4f}")
    print(f"  Clamped vs Observed:   {diagnostics['mae_comparisons']['clamped_vs_observed']:.4f}")
    
    if diagnostics['scale_compatibility_assessment']['clipping_dominates']:
        print("\n  ⚠ CLIPPING DOMINATES: >50% of predictions hit bounds")
        print("  The constrained mapping is fundamentally mismatched to the target scale.")
    
    return diagnostics


# =============================================================================
# STEP 3: FIX ABLATION LOGIC
# =============================================================================

def predict_with_feature_subset(
    D_l: float,
    D_sys: float,
    T_legs: float,
    params: ObservationMappingParams,
    lift: str,
    active_features: Tuple[bool, bool, bool]
) -> float:
    """
    Predict with only specified features active.
    
    Args:
        active_features: (use_D_l, use_D_sys, use_T_legs) - which features to include
    
    This is the CORRECTED version that truly zeros out coefficients for inactive features.
    """
    use_D_l, use_D_sys, use_T_legs = active_features
    
    # Base intercept
    intercept = params.a
    if lift and params.per_lift_a and lift in params.per_lift_a:
        intercept = params.per_lift_a[lift]
    
    # Only include fatigue terms for ACTIVE features
    fatigue_terms = 0.0
    if use_D_l:
        fatigue_terms += params.b_l * max(0.0, 1.0 - D_l)
    if use_D_sys:
        fatigue_terms += params.b_sys * max(0.0, 1.0 - D_sys)
    if use_T_legs:
        fatigue_terms += params.b_t * max(0.0, 1.0 - T_legs)
    
    pred = intercept + fatigue_terms
    return max(params.y_min, min(params.y_max, pred))


def calibrate_with_feature_subset(
    rows: List[Dict],
    active_features: Tuple[bool, bool, bool],
    grid_steps: int = 6,
    refinement_steps: int = 1
) -> Tuple[ObservationMappingParams, float]:
    """
    Calibrate with only specified features active.
    
    Args:
        active_features: (use_D_l, use_D_sys, use_T_legs) - which features to include
    """
    use_D_l, use_D_sys, use_T_legs = active_features
    
    def compute_mae_for_params(params: ObservationMappingParams) -> float:
        errors = []
        for row in rows:
            pred = predict_with_feature_subset(
                D_l=row.get('D_l', 0.0),
                D_sys=row.get('D_sys', 0.0),
                T_legs=row.get('T_legs', 0.0),
                params=params,
                lift=row.get('lift'),
                active_features=active_features
            )
            errors.append(abs(pred - row['observed']))
        return statistics.mean(errors) if errors else float('inf')
    
    # Grid search
    best_params = ObservationMappingParams.default_params()
    best_mae = compute_mae_for_params(best_params)
    
    # Define search ranges based on which features are active
    a_range = [0.2, 0.4, 0.6, 0.8, 1.0]
    coeff_range = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5]
    
    for a in a_range:
        for b_l in coeff_range if use_D_l else [0.0]:
            for b_sys in coeff_range if use_D_sys else [0.0]:
                for b_t in coeff_range if use_T_legs else [0.0]:
                    params = ObservationMappingParams(
                        a=a, b_l=b_l, b_sys=b_sys, b_t=b_t,
                        y_min=0.60, y_max=1.10
                    )
                    mae = compute_mae_for_params(params)
                    if mae < best_mae:
                        best_mae = mae
                        best_params = params
    
    return best_params, best_mae


def compute_state_ablation_fixed(rows):
    """
    FIXED state ablation with proper feature masking.
    """
    print("\n" + "=" * 80)
    print("STEP 3: Fixed State Ablation / Additive Value Test")
    print("=" * 80)
    
    # Prepare rows with 'observed' key for calibration
    prepared_rows = []
    for row in rows:
        new_row = dict(row)
        new_row['observed'] = row['observed_perf_y']
        prepared_rows.append(new_row)
    
    # Define ablation configs
    ablation_configs = [
        ((False, False, True), "T_legs_only"),
        ((True, False, False), "D_l_only"),
        ((False, True, False), "D_sys_only"),
        ((True, True, False), "D_l_plus_D_sys"),
        ((True, False, True), "D_l_plus_T_legs"),
        ((False, True, True), "D_sys_plus_T_legs"),
        ((True, True, True), "D_l_plus_D_sys_plus_T_legs"),
    ]
    
    results = []
    for active_features, name in ablation_configs:
        params, mae = calibrate_with_feature_subset(prepared_rows, active_features, grid_steps=6, refinement_steps=1)
        
        results.append({
            'features': name,
            'active_mask': active_features,
            'mae': round(mae, 4),
            'params': {
                'a': round(params.a, 4),
                'b_l': round(params.b_l, 4),
                'b_sys': round(params.b_sys, 4),
                'b_t': round(params.b_t, 4),
            }
        })
    
    # Print results
    print("\nFixed State Ablation Results:")
    print(f"{'Features':<25} {'MAE':<10} {'a':<8} {'b_l':<8} {'b_sys':<8} {'b_t':<8}")
    print("-" * 80)
    for r in results:
        p = r['params']
        print(f"{r['features']:<25} {r['mae']:<10.4f} {p['a']:<8.4f} {p['b_l']:<8.4f} {p['b_sys']:<8.4f} {p['b_t']:<8.4f}")
    
    # Compute additive value
    baseline_mae = next(r['mae'] for r in results if r['features'] == "T_legs_only")
    full_mae = next(r['mae'] for r in results if r['features'] == "D_l_plus_D_sys_plus_T_legs")
    
    print(f"\nAdditive Value Analysis:")
    print(f"  T_legs only MAE: {baseline_mae:.4f}")
    print(f"  Full model MAE:  {full_mae:.4f}")
    print(f"  Improvement:     {baseline_mae - full_mae:.4f} ({(baseline_mae - full_mae)/baseline_mae*100:.1f}%)")
    
    return {'ablations': results, 'additive_improvement': round(baseline_mae - full_mae, 4)}


# =============================================================================
# STEP 4: RERUN DIAGNOSTICS WITH CORRECTED TOOLING
# =============================================================================

def extract_diagnostic_dataset():
    """Extract diagnostic dataset from replay."""
    print("=" * 80)
    print("STEP 4: Extracting Diagnostic Dataset")
    print("=" * 80)
    
    artifacts_dir = Path("./artifacts/synth_v2_run_v4_3")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    db = SessionLocal()
    try:
        runner = ReplayRunner(db, artifacts_dir=str(artifacts_dir))
        date_from = date(2026, 1, 1)
        date_to = date(2026, 3, 31)
        
        runner.replay(athlete_id=299, date_from=date_from, date_to=date_to, dry_run=True)
        
        from app.services.engine_orchestrator import EngineOrchestrator
        orchestrator = EngineOrchestrator(db)
        
        diagnostic_rows = []
        for error_row in runner.day_errors:
            session_date = date.fromisoformat(error_row['date'])
            lift = error_row['lift']
            day_state = orchestrator.get_day_state_snapshot(299, session_date)
            
            if day_state:
                lift_state = day_state.per_lift.get(lift, None)
                D_l = getattr(lift_state, 'D_l', 0.0) if lift_state else 0.0
                D_sys = day_state.D_sys
                T_legs = getattr(day_state, 'T_legs', 0.0)
                E_fat = getattr(day_state, 'E_fat', 0.0)
                R_mito = getattr(day_state, 'R_mito', 0.0)
            else:
                D_l = D_sys = T_legs = E_fat = R_mito = 0.0
            
            diagnostic_rows.append({
                'date': error_row['date'],
                'lift': lift,
                'observed_perf_y': error_row['observed'],
                'D_l': D_l,
                'D_sys': D_sys,
                'T_legs': T_legs,
                'E_fat': E_fat,
                'R_mito': R_mito,
            })
        
        # Write to CSV
        csv_path = artifacts_dir / "day_state_diagnostics.csv"
        if diagnostic_rows:
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=diagnostic_rows[0].keys())
                writer.writeheader()
                writer.writerows(diagnostic_rows)
            print(f"  Wrote {len(diagnostic_rows)} rows to {csv_path}")
        
        return diagnostic_rows, artifacts_dir
    finally:
        db.close()


# =============================================================================
# STEP 5: GENERATE TRUSTWORTHY RECOMMENDATION
# =============================================================================

def generate_trustworthy_recommendation(target_def, scale_diagnostics, ablation_results, rows):
    """Generate recommendation based on corrected diagnostics."""
    print("\n" + "=" * 80)
    print("STEP 5: Trustworthy Diagnostic Interpretation")
    print("=" * 80)
    
    # Feature-target correlations
    observed = [r['observed_perf_y'] for r in rows]
    D_l = [r['D_l'] for r in rows]
    D_sys = [r['D_sys'] for r in rows]
    T_legs = [r['T_legs'] for r in rows]
    
    T_legs_corr = abs(pearson_correlation(T_legs, observed))
    D_l_corr = abs(pearson_correlation(D_l, observed))
    D_sys_corr = abs(pearson_correlation(D_sys, observed))
    
    # Extract key findings
    clipping_fraction = scale_diagnostics['clipping_frequency']['total_clipped']['fraction']
    observed_mean = scale_diagnostics['observed_target_distribution']['mean']
    mapping_bounds = scale_diagnostics['constrained_mapping_bounds']
    
    print("\n1. TARGET-SCALE CRISIS:")
    print(f"   Observed target mean: {observed_mean:.4f}")
    print(f"   Mapping bounds: [{mapping_bounds['y_min']}, {mapping_bounds['y_max']}]")
    print(f"   Clipping frequency: {clipping_fraction*100:.1f}%")
    
    if clipping_fraction > 0.5:
        print("   ⚠⚠⚠ CRITICAL: Target scale is INCOMPATIBLE with mapping bounds")
        print("   All MAE comparisons are MEANINGLESS until this is fixed.")
    
    print("\n2. FEATURE CORRELATIONS (raw, uncorrected for scale mismatch):")
    print(f"   |r(T_legs, target)| = {T_legs_corr:.4f}")
    print(f"   |r(D_l, target)|    = {D_l_corr:.4f}")
    print(f"   |r(D_sys, target)|  = {D_sys_corr:.4f}")
    
    T_legs_dominant = T_legs_corr > D_l_corr * 1.5 and T_legs_corr > D_sys_corr * 1.5
    if T_legs_dominant:
        print("   → T_legs is the most predictive feature (1.5x threshold)")
    else:
        print("   → No single feature dominates")
    
    print("\n3. STATE ABLATION (FIXED):")
    for r in ablation_results['ablations']:
        print(f"   {r['features']:<25}: MAE={r['mae']:.4f}")
    
    print("\n" + "=" * 80)
    print("TRUSTWORTHY RECOMMENDATION:")
    print("=" * 80)
    
    if clipping_fraction > 0.5:
        print("\n🚨 PRIMARY ISSUE: FUNDAMENTAL SCALE MISMATCH 🚨")
        print("\nThe synthetic dataset's observed_perf_y has mean ~1.8, max ~4.7")
        print("But the constrained mapping is bounded to [0.60, 1.10]")
        print("This means >50% of predictions hit the bounds, making MAE meaningless.")
        print("\nNEXT STEP OPTIONS:")
        print("A) ADJUST MAPPING BOUNDS to match observed target range [0.8, 4.7]")
        print("B) REGENERATE SYNTHETIC DATASET with perf_y in [0.8, 1.1] range")
        print("C) RECALIBRATE OBSERVED_PERF_Y extraction to produce velocity ratios in [0.8, 1.1]")
        
        recommendation = 'fix_scale_mismatch_first'
    else:
        print("\n✓ Scale mismatch is manageable")
        print("\nNEXT STEP:")
        if T_legs_dominant:
            print("Investigate why T_legs dominates D_l/D_sys")
        else:
            print("All features contribute - proceed with rescaling")
        recommendation = 'proceed_with_rescaling'
    
    return {
        'critical_issue': 'scale_mismatch' if clipping_fraction > 0.5 else 'none',
        'clipping_fraction': clipping_fraction,
        'T_legs_dominant': T_legs_dominant,
        'T_legs_correlation': round(T_legs_corr, 4),
        'D_l_correlation': round(D_l_corr, 4),
        'D_sys_correlation': round(D_sys_corr, 4),
        'recommendation': recommendation,
        'target_mean': round(observed_mean, 4),
        'mapping_bounds': mapping_bounds,
    }


def main():
    print("\n" + "=" * 80)
    print("SPRINT V4.3: Fix Observation Diagnostics for Trustworthiness")
    print("=" * 80)
    
    # Step 4: Extract dataset (run first to get data)
    rows, artifacts_dir = extract_diagnostic_dataset()
    print(f"Loaded {len(rows)} diagnostic rows")
    
    # Step 1: Trace target construction
    target_def = trace_target_construction(rows)
    with open(artifacts_dir / "target_definition.json", 'w') as f:
        json.dump(target_def, f, indent=2)
    
    # Step 2: Target-scale consistency checks
    scale_diagnostics = analyze_target_scale_consistency(rows)
    with open(artifacts_dir / "target_scale_diagnostics.json", 'w') as f:
        json.dump(scale_diagnostics, f, indent=2)
    
    # Step 3: Fixed state ablation
    ablation_results = compute_state_ablation_fixed(rows)
    with open(artifacts_dir / "state_ablation_fixed.json", 'w') as f:
        json.dump(ablation_results, f, indent=2)
    
    # Step 5: Trustworthy recommendation
    recommendation = generate_trustworthy_recommendation(target_def, scale_diagnostics, ablation_results, rows)
    with open(artifacts_dir / "trustworthy_recommendation.json", 'w') as f:
        json.dump(recommendation, f, indent=2)
    
    print("\n" + "=" * 80)
    print("SPRINT V4.3 COMPLETE")
    print("=" * 80)
    print(f"\nArtifacts generated in: {artifacts_dir}")
    print("  - day_state_diagnostics.csv")
    print("  - target_definition.json")
    print("  - target_scale_diagnostics.json")
    print("  - state_ablation_fixed.json")
    print("  - trustworthy_recommendation.json")


if __name__ == "__main__":
    main()
