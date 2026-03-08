"""
Sprint V4.2: Diagnostic Analysis of D_l, D_sys Signal Quality

Diagnose why D_l and D_sys contribute little/nothing to the operational observation mapping.
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


def pearson_correlation(x: List[float], y: List[float]) -> float:
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


def spearman_correlation(x: List[float], y: List[float]) -> float:
    """Compute Spearman rank correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    def rank(vals: List[float]) -> List[float]:
        sorted_vals = sorted(enumerate(vals), key=lambda t: t[1])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(sorted_vals):
            j = i
            while j < len(sorted_vals) and sorted_vals[j][1] == sorted_vals[i][1]:
                j += 1
            avg_rank = (i + j + 1) / 2.0
            for k in range(i, j):
                ranks[sorted_vals[k][0]] = avg_rank
            i = j
        return ranks
    return pearson_correlation(rank(x), rank(y))


def compute_mae(predictions, observed):
    """Compute MAE."""
    return statistics.mean([abs(p - o) for p, o in zip(predictions, observed)])


def extract_diagnostic_dataset():
    """Build diagnostic dataset from replay/validation path."""
    print("=" * 80)
    print("STEP 1: Extracting Diagnostic Dataset")
    print("=" * 80)
    
    artifacts_dir = Path("./artifacts/synth_v2_run_v4_2")
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
                'legacy_pred': error_row.get('predicted_legacy', error_row['predicted_model']),
                'constrained_pred': error_row.get('predicted_constrained', error_row['predicted_model']),
                'absolute_error_legacy': abs(error_row['observed'] - error_row.get('predicted_legacy', error_row['predicted_model'])),
                'absolute_error_constrained': abs(error_row['observed'] - error_row.get('predicted_constrained', error_row['predicted_model'])),
                'D_l': D_l,
                'D_sys': D_sys,
                'T_legs': T_legs,
                'E_fat': E_fat,
                'R_mito': R_mito,
            })
        
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


def compute_scaling_summary(rows):
    """Compute signal magnitude and scaling statistics."""
    print("\n" + "=" * 80)
    print("STEP 2: Signal Magnitude / Scaling Analysis")
    print("=" * 80)
    
    D_l_vals = [r['D_l'] for r in rows]
    D_sys_vals = [r['D_sys'] for r in rows]
    T_legs_vals = [r['T_legs'] for r in rows]
    
    summary = {
        'raw_features': {
            'D_l': compute_descriptive_stats(D_l_vals),
            'D_sys': compute_descriptive_stats(D_sys_vals),
            'T_legs': compute_descriptive_stats(T_legs_vals),
        },
        'one_minus_features': {
            '(1 - D_l)': compute_descriptive_stats([1 - v for v in D_l_vals]),
            '(1 - D_sys)': compute_descriptive_stats([1 - v for v in D_sys_vals]),
            '(1 - T_legs)': compute_descriptive_stats([1 - v for v in T_legs_vals]),
        },
        'observed_perf_y': compute_descriptive_stats([r['observed_perf_y'] for r in rows]),
        'by_lift': {},
    }
    
    lifts = list(set(r['lift'] for r in rows))
    for lift in lifts:
        lift_rows = [r for r in rows if r['lift'] == lift]
        summary['by_lift'][lift] = {
            'D_l': compute_descriptive_stats([r['D_l'] for r in lift_rows]),
            'D_sys': compute_descriptive_stats([r['D_sys'] for r in lift_rows]),
            'T_legs': compute_descriptive_stats([r['T_legs'] for r in lift_rows]),
            'n_samples': len(lift_rows),
        }
    
    print("\nGlobal Feature Statistics:")
    print(f"  D_l:     mean={summary['raw_features']['D_l']['mean']:.4f}, std={summary['raw_features']['D_l']['std']:.4f}")
    print(f"  D_sys:   mean={summary['raw_features']['D_sys']['mean']:.4f}, std={summary['raw_features']['D_sys']['std']:.4f}")
    print(f"  T_legs:  mean={summary['raw_features']['T_legs']['mean']:.4f}, std={summary['raw_features']['T_legs']['std']:.4f}")
    
    print("\nPer-Lift D_l Variance:")
    for lift, stats in sorted(summary['by_lift'].items()):
        print(f"  {lift}: std={stats['D_l']['std']:.4f}, n={stats['n_samples']}")
    
    return summary


def compute_feature_target_correlations(rows):
    """Compute correlations between features and observed_perf_y."""
    print("\n" + "=" * 80)
    print("STEP 3: Feature-to-Target Association Analysis")
    print("=" * 80)
    
    observed = [r['observed_perf_y'] for r in rows]
    D_l = [r['D_l'] for r in rows]
    D_sys = [r['D_sys'] for r in rows]
    T_legs = [r['T_legs'] for r in rows]
    
    global_corr = {
        'D_l': {'pearson': round(pearson_correlation(D_l, observed), 4), 'spearman': round(spearman_correlation(D_l, observed), 4)},
        'D_sys': {'pearson': round(pearson_correlation(D_sys, observed), 4), 'spearman': round(spearman_correlation(D_sys, observed), 4)},
        'T_legs': {'pearson': round(pearson_correlation(T_legs, observed), 4), 'spearman': round(spearman_correlation(T_legs, observed), 4)},
        '(1 - D_l)': {'pearson': round(pearson_correlation([1 - v for v in D_l], observed), 4), 'spearman': round(spearman_correlation([1 - v for v in D_l], observed), 4)},
        '(1 - D_sys)': {'pearson': round(pearson_correlation([1 - v for v in D_sys], observed), 4), 'spearman': round(spearman_correlation([1 - v for v in D_sys], observed), 4)},
        '(1 - T_legs)': {'pearson': round(pearson_correlation([1 - v for v in T_legs], observed), 4), 'spearman': round(spearman_correlation([1 - v for v in T_legs], observed), 4)},
    }
    
    print("\nGlobal Correlations (Pearson / Spearman):")
    for feature, corr in global_corr.items():
        print(f"  {feature:12s}: {corr['pearson']:+.4f} / {corr['spearman']:+.4f}")
    
    return {'global': global_corr}


def compute_collinearity_analysis(rows):
    """Analyze collinearity among D_l, D_sys, T_legs."""
    print("\n" + "=" * 80)
    print("STEP 4: Collinearity / Redundancy Analysis")
    print("=" * 80)
    
    D_l = [r['D_l'] for r in rows]
    D_sys = [r['D_sys'] for r in rows]
    T_legs = [r['T_legs'] for r in rows]
    observed = [r['observed_perf_y'] for r in rows]
    
    pairwise = {
        'D_l_vs_D_sys': {'pearson': round(pearson_correlation(D_l, D_sys), 4), 'spearman': round(spearman_correlation(D_l, D_sys), 4)},
        'D_l_vs_T_legs': {'pearson': round(pearson_correlation(D_l, T_legs), 4), 'spearman': round(spearman_correlation(D_l, T_legs), 4)},
        'D_sys_vs_T_legs': {'pearson': round(pearson_correlation(D_sys, T_legs), 4), 'spearman': round(spearman_correlation(D_sys, T_legs), 4)},
    }
    
    def r_squared(x, others):
        if len(others) == 1:
            r = pearson_correlation(x, others[0])
            return r ** 2
        return sum(pearson_correlation(x, o) ** 2 for o in others) / len(others)
    
    vif_proxy = {
        'D_l': round(1 / (1 - r_squared(D_l, [D_sys, T_legs]) + 1e-10), 4),
        'D_sys': round(1 / (1 - r_squared(D_sys, [D_l, T_legs]) + 1e-10), 4),
        'T_legs': round(1 / (1 - r_squared(T_legs, [D_l, D_sys]) + 1e-10), 4),
    }
    
    print("\nPairwise Correlations (Pearson / Spearman):")
    for pair, corr in pairwise.items():
        print(f"  {pair:20s}: {corr['pearson']:+.4f} / {corr['spearman']:+.4f}")
    
    print("\nVIF Proxy (higher = more collinear):")
    for var, vif in vif_proxy.items():
        print(f"  {var}: {vif:.4f}")
    
    return {'pairwise_correlations': pairwise, 'vif_proxy': vif_proxy}


def evaluate_mapping_variant(rows, variant_name, transform_fn):
    """Evaluate a feature variant by recalibrating constrained mapping."""
    transformed_rows = []
    for row in rows:
        new_row = dict(row)
        D_l, D_sys, T_legs = row['D_l'], row['D_sys'], row['T_legs']
        f1, f2, f3 = transform_fn(D_l, D_sys, T_legs, row['lift'])
        new_row['D_l'] = f1
        new_row['D_sys'] = f2
        new_row['T_legs'] = f3
        new_row['observed'] = row['observed_perf_y']  # Calibration expects 'observed'
        transformed_rows.append(new_row)
    
    calibration_result = calibrate_observation_mapping(transformed_rows, per_lift=False, grid_steps=6, refinement_steps=2)
    
    predictions = []
    observed = []
    for row in transformed_rows:
        pred = predict_perf_y_constrained(D_l=row['D_l'], D_sys=row['D_sys'], T_legs=row['T_legs'], params=calibration_result.params, lift=row['lift'])
        predictions.append(pred)
        observed.append(row['observed_perf_y'])
    
    mae = compute_mae(predictions, observed)
    return {'variant': variant_name, 'params': calibration_result.params.to_dict(), 'mae': round(mae, 4)}


def compute_normalization_ablation(rows):
    """Test different normalization strategies."""
    print("\n" + "=" * 80)
    print("STEP 5: Normalization / Reparameterization Diagnostic")
    print("=" * 80)
    
    D_l_vals = [r['D_l'] for r in rows]
    D_sys_vals = [r['D_sys'] for r in rows]
    T_legs_vals = [r['T_legs'] for r in rows]
    
    D_l_mean, D_l_std = statistics.mean(D_l_vals), statistics.stdev(D_l_vals)
    D_sys_mean, D_sys_std = statistics.mean(D_sys_vals), statistics.stdev(D_sys_vals)
    T_legs_mean, T_legs_std = statistics.mean(T_legs_vals), statistics.stdev(T_legs_vals)
    
    def raw_transform(D_l, D_sys, T_legs, lift):
        return (1 - D_l, 1 - D_sys, 1 - T_legs)
    
    def zscore_transform(D_l, D_sys, T_legs, lift):
        z_D_l = (1 - D_l - (1 - D_l_mean)) / (D_l_std + 1e-10)
        z_D_sys = (1 - D_sys - (1 - D_sys_mean)) / (D_sys_std + 1e-10)
        z_T_legs = (1 - T_legs - (1 - T_legs_mean)) / (T_legs_std + 1e-10)
        return (z_D_l, z_D_sys, z_T_legs)
    
    results = [
        evaluate_mapping_variant(rows, "A_raw_one_minus", raw_transform),
        evaluate_mapping_variant(rows, "B_zscored", zscore_transform),
    ]
    
    print("\nNormalization Ablation Results:")
    print(f"{'Variant':<30} {'MAE':<10} {'a':<8} {'b_l':<8} {'b_sys':<8} {'b_t':<8}")
    print("-" * 80)
    for r in results:
        p = r['params']
        print(f"{r['variant']:<30} {r['mae']:<10.4f} {p['a']:<8.4f} {p['b_l']:<8.4f} {p['b_sys']:<8.4f} {p['b_t']:<8.4f}")
    
    return {'variants': results}


def fit_and_eval_ablation(rows, feature_mask, name):
    """Fit with only selected features."""
    use_D_l, use_D_sys, use_T_legs = feature_mask
    masked_rows = []
    for row in rows:
        new_row = dict(row)
        if not use_D_l:
            new_row['D_l'] = 0.0
        if not use_D_sys:
            new_row['D_sys'] = 0.0
        if not use_T_legs:
            new_row['T_legs'] = 0.0
        new_row['observed'] = row['observed_perf_y']  # Calibration expects 'observed'
        masked_rows.append(new_row)
    
    calibration_result = calibrate_observation_mapping(masked_rows, per_lift=False, grid_steps=6, refinement_steps=2)
    
    predictions = []
    observed = []
    for row in masked_rows:
        pred = predict_perf_y_constrained(D_l=row['D_l'], D_sys=row['D_sys'], T_legs=row['T_legs'], params=calibration_result.params, lift=row['lift'])
        predictions.append(pred)
        observed.append(row['observed_perf_y'])
    
    mae = compute_mae(predictions, observed)
    return {'features': name, 'mae': round(mae, 4), 'params': calibration_result.params.to_dict()}


def compute_state_ablation(rows):
    """Measure incremental value of each state."""
    print("\n" + "=" * 80)
    print("STEP 6: State Ablation / Additive Value Test")
    print("=" * 80)
    
    results = [
        fit_and_eval_ablation(rows, (False, False, True), "T_legs_only"),
        fit_and_eval_ablation(rows, (True, False, False), "D_l_only"),
        fit_and_eval_ablation(rows, (False, True, False), "D_sys_only"),
        fit_and_eval_ablation(rows, (True, True, False), "D_l_plus_D_sys"),
        fit_and_eval_ablation(rows, (True, False, True), "D_l_plus_T_legs"),
        fit_and_eval_ablation(rows, (False, True, True), "D_sys_plus_T_legs"),
        fit_and_eval_ablation(rows, (True, True, True), "D_l_plus_D_sys_plus_T_legs"),
    ]
    
    print("\nState Ablation Results:")
    print(f"{'Features':<25} {'MAE':<10} {'a':<8} {'b_l':<8} {'b_sys':<8} {'b_t':<8}")
    print("-" * 80)
    for r in results:
        p = r['params']
        print(f"{r['features']:<25} {r['mae']:<10.4f} {p['a']:<8.4f} {p['b_l']:<8.4f} {p['b_sys']:<8.4f} {p['b_t']:<8.4f}")
    
    baseline_mae = next(r['mae'] for r in results if r['features'] == "T_legs_only")
    full_mae = next(r['mae'] for r in results if r['features'] == "D_l_plus_D_sys_plus_T_legs")
    
    print(f"\nAdditive Value: T_legs only={baseline_mae:.4f}, Full={full_mae:.4f}, Improvement={baseline_mae - full_mae:.4f}")
    
    return {'ablations': results, 'additive_improvement': round(baseline_mae - full_mae, 4)}


def generate_interpretation(scaling, correlations, collinearity, normalization, ablation):
    """Generate diagnostic interpretation and recommendation."""
    print("\n" + "=" * 80)
    print("STEP 7: DIAGNOSTIC INTERPRETATION")
    print("=" * 80)
    
    # Extract key metrics
    D_l_std = scaling['raw_features']['D_l']['std']
    D_sys_std = scaling['raw_features']['D_sys']['std']
    T_legs_std = scaling['raw_features']['T_legs']['std']
    
    T_legs_corr = abs(correlations['global']['T_legs']['pearson'])
    D_l_corr = abs(correlations['global']['D_l']['pearson'])
    D_sys_corr = abs(correlations['global']['D_sys']['pearson'])
    
    D_l_T_legs_corr = abs(collinearity['pairwise_correlations']['D_l_vs_T_legs']['pearson'])
    D_sys_T_legs_corr = abs(collinearity['pairwise_correlations']['D_sys_vs_T_legs']['pearson'])
    
    ablation_improvement = ablation['additive_improvement']
    
    # Analysis
    print("\n1. SIGNAL QUALITY ANALYSIS:")
    
    scaling_issue = D_l_std < T_legs_std * 0.5 or D_sys_std < T_legs_std * 0.5
    if scaling_issue:
        print("   ⚠ SCALING ISSUE DETECTED: D_l or D_sys have much lower variance than T_legs")
        print(f"      D_l std={D_l_std:.4f}, D_sys std={D_sys_std:.4f}, T_legs std={T_legs_std:.4f}")
    else:
        print("   ✓ Variance levels are comparable across features")
    
    collinearity_issue = D_l_T_legs_corr > 0.7 or D_sys_T_legs_corr > 0.7
    print("\n2. COLLINEARITY ANALYSIS:")
    if collinearity_issue:
        print("   ⚠ COLLINEARITY ISSUE DETECTED: Strong correlation with T_legs")
        print(f"      D_l↔T_legs: r={D_l_T_legs_corr:.3f}, D_sys↔T_legs: r={D_sys_T_legs_corr:.3f}")
    else:
        print("   ✓ Moderate collinearity - not the primary cause of zero weights")
    
    print("\n3. PREDICTIVE VALUE ANALYSIS:")
    T_legs_dominant = T_legs_corr > D_l_corr * 2 and T_legs_corr > D_sys_corr * 2
    if T_legs_dominant:
        print("   ⚠ T_legs is much more predictive than D_l/D_sys")
        print(f"      |r(T_legs)|={T_legs_corr:.3f}, |r(D_l)|={D_l_corr:.3f}, |r(D_sys)|={D_sys_corr:.3f}")
    else:
        print("   ✓ All features show similar correlation with target")
    
    print("\n4. ADDITIVE VALUE ANALYSIS:")
    if ablation_improvement < 0.001:
        print("   ⚠ Adding D_l/D_sys provides minimal improvement over T_legs alone")
        print(f"      Improvement: {ablation_improvement:.4f} MAE reduction")
    else:
        print(f"   ✓ D_l/D_sys add value: {ablation_improvement:.4f} MAE reduction")
    
    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION FOR NEXT SPRINT:")
    print("=" * 80)
    
    if scaling_issue and not collinearity_issue:
        print("\n→ NEXT STEP: A) FEATURE RESCALING")
        print("   The synthetic dataset has D_l/D_sys on a different scale than T_legs.")
        print("   Recalibrate with normalized features or rescale in the day engine.")
    elif collinearity_issue and not T_legs_dominant:
        print("\n→ NEXT STEP: B) PER-LIFT OBSERVATION MAPPING")
        print("   High collinearity suggests D_l/D_sys capture similar variance as T_legs.")
        print("   Consider per-lift intercepts or hierarchical calibration.")
    elif T_legs_dominant:
        print("\n→ NEXT STEP: C) SIMPLIFYING/REMOVING STATES")
        print("   The synthetic dataset primarily encodes performance through T_legs.")
        print("   Consider: (1) simpler model with just T_legs, or (2) regenerate dataset")
        print("   with more independent variation in D_l/D_sys.")
    else:
        print("\n→ NEXT STEP: D) REGENERATE SYNTHETIC DATASET")
        print("   The current dataset may not stress D_l/D_sys sufficiently.")
        print("   Consider regenerating with more targeted variation in local/systemic fatigue.")
    
    return {
        'scaling_issue': scaling_issue,
        'collinearity_issue': collinearity_issue,
        'T_legs_dominant': T_legs_dominant,
        'additive_improvement': ablation_improvement,
    }


def main():
    print("\n" + "=" * 80)
    print("SPRINT V4.2: Diagnostic Analysis of D_l, D_sys Signal Quality")
    print("=" * 80)
    
    # Step 1: Extract dataset
    rows, artifacts_dir = extract_diagnostic_dataset()
    
    # Step 2: Signal magnitude analysis
    scaling_summary = compute_scaling_summary(rows)
    with open(artifacts_dir / "feature_scaling_summary.json", 'w') as f:
        json.dump(scaling_summary, f, indent=2)
    
    # Step 3: Feature-target correlations
    correlations = compute_feature_target_correlations(rows)
    with open(artifacts_dir / "feature_target_correlations.json", 'w') as f:
        json.dump(correlations, f, indent=2)
    
    # Step 4: Collinearity analysis
    collinearity = compute_collinearity_analysis(rows)
    with open(artifacts_dir / "feature_collinearity.json", 'w') as f:
        json.dump(collinearity, f, indent=2)
    
    # Step 5: Normalization ablation
    normalization = compute_normalization_ablation(rows)
    with open(artifacts_dir / "normalization_ablation.json", 'w') as f:
        json.dump(normalization, f, indent=2)
    
    # Step 6: State ablation
    ablation = compute_state_ablation(rows)
    with open(artifacts_dir / "state_ablation.json", 'w') as f:
        json.dump(ablation, f, indent=2)
    
    # Step 7: Interpretation
    interpretation = generate_interpretation(scaling_summary, correlations, collinearity, normalization, ablation)
    
    # Save interpretation
    with open(artifacts_dir / "diagnostic_interpretation.json", 'w') as f:
        json.dump(interpretation, f, indent=2)
    
    print("\n" + "=" * 80)
    print("SPRINT V4.2 COMPLETE")
    print("=" * 80)
    print(f"\nArtifacts generated in: {artifacts_dir}")
    print("  - day_state_diagnostics.csv")
    print("  - feature_scaling_summary.json")
    print("  - feature_target_correlations.json")
    print("  - feature_collinearity.json")
    print("  - normalization_ablation.json")
    print("  - state_ablation.json")
    print("  - diagnostic_interpretation.json")


if __name__ == "__main__":
    main()
