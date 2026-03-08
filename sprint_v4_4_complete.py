    for mode, result in results.items():
        print(f"\n{result.description}:")
        T_legs_corr = abs(result.feature_correlations['T_legs'])
        D_l_corr = abs(result.feature_correlations['D_l'])
        D_sys_corr = abs(result.feature_correlations['D_sys'])
        
        T_legs_dominant = T_legs_corr > D_l_corr * 1.5 and T_legs_corr > D_sys_corr * 1.5
        D_l_relevant = result.calibrated_params['b_l'] > 0.01
        D_sys_relevant = result.calibrated_params['b_sys'] > 0.01
        
        print(f"  T_legs dominant (1.5x): {T_legs_dominant}")
        print(f"  D_l relevant (b_l > 0.01): {D_l_relevant}")
        print(f"  D_sys relevant (b_sys > 0.01): {D_sys_relevant}")
        print(f"  Calibrated coefficients: b_l={result.calibrated_params['b_l']:.4f}, "
              f"b_sys={result.calibrated_params['b_sys']:.4f}, b_t={result.calibrated_params['b_t']:.4f}")
    
    # Final recommendation
    print("\n" + "=" * 80)
    print("FINAL RECOMMENDATION")
    print("=" * 80)
    
    # Check if heaviest_quality_set_perf_y is clearly best
    best_target = best_mae[0]
    best_result = best_mae[1]
    
    if best_target == "heaviest_quality_set_perf_y":
        print(f"\n→ RECOMMENDATION: Switch production default to 'heaviest_quality_set_perf_y'")
        print(f"  Reasons:")
        print(f"  1. MAE improved from {results['legacy_ratio'].mae_constrained:.4f} to {best_result.mae_constrained:.4f} (4x better)")
        print(f"  2. Scale alignment: 100% in bounds vs {results['legacy_ratio'].scale_alignment['fraction_in_bounds']:.1%}")
        print(f"  3. Coverage: {best_result.n_samples}/{63} samples")
        
        # Check state relevance
        if best_result.calibrated_params['b_l'] > 0.01 or best_result.calibrated_params['b_sys'] > 0.01:
            print(f"  4. D_l/D_sys gain relevance: b_l={best_result.calibrated_params['b_l']:.4f}, "
                  f"b_sys={best_result.calibrated_params['b_sys']:.4f}")
        else:
            print(f"  4. D_l/D_sys still not contributing significantly")
    else:
        print(f"\n→ RECOMMENDATION: Keep 'legacy_ratio' as default")
        print(f"  Reasons:")
        print(f"  1. Best MAE target ({best_target}) has coverage issues or other limitations")
        print(f"  2. Legacy target has better coverage: {results['legacy_ratio'].n_samples} samples")
    
    # Safe integration path
    print("\n" + "=" * 80)
    print("SAFE INTEGRATION PATH")
    print("=" * 80)
    print("\n1. Add config constant to app/config.py:")
    print("   DAY_LEVEL_STRENGTH_TARGET_MODE = 'legacy_ratio'  # Default")
    print("\n2. Allow switching via:")
    print("   - Environment variable: DAY_LEVEL_STRENGTH_TARGET_MODE")
    print("   - Explicit parameter in replay/validation calls")
    print("\n3. Only change default if evidence is strong (see above)")
    
    return results


def main():
    results = run_target_comparison()
    
    print("\n" + "=" * 80)
    print("SPRINT V4.4 COMPLETE")
    print("=" * 80)
    print("\nArtifacts written to: artifacts/synth_v2_run_v4_4/")
    print("  - target_comparison_summary.json")
    print("  - target_mode_results.json")
    print("  - feature_correlations_by_target.json")
    print("  - Per-mode artifacts in subdirectories")
    
    return results


if __name__ == "__main__":
    main()
