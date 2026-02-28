#!/usr/bin/env python3
"""
RPE-based model validation for concurrent-training.

Validates model fatigue predictions against subjective RPE scores.
"""
import json
import csv
from pathlib import Path
from collections import defaultdict
import statistics
import math

import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.database import SessionLocal
from app import models

def compute_correlation(x, y):
    """Compute Pearson correlation coefficient."""
    if len(x) != len(y) or len(x) < 2:
        return None
    
    try:
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)
        
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        
        if denom_x == 0 or denom_y == 0:
            return None
        
        return numerator / (denom_x * denom_y)
    except:
        return None

def main():
    db = SessionLocal()
    athlete_id = 1
    
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    
    print('='*70)
    print('RPE-BASED MODEL VALIDATION')
    print('='*70)
    
    # Get all sessions with their RPE data
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).order_by(models.StrengthSession.start_time).all()
    
    # Collect RPE data and correlate with model fatigue
    rpe_analysis = []
    rpe_values = []
    d_sys_values = []
    d_l_values = []
    t_legs_values = []
    
    lift_specific = defaultdict(lambda: {'rpe': [], 'd_l': [], 'tonnage': []})
    
    for s in sessions:
        raw = s.raw_data or {}
        sets = raw.get('sets', [])
        
        # Get RPE from first set (session-level RPE)
        session_rpe = None
        for set_data in sets:
            rpe = set_data.get('rpe')
            if rpe is not None and rpe > 0:
                session_rpe = rpe
                break
        
        if session_rpe is None:
            continue  # Skip sessions without RPE
        
        # Get day state for this session
        date_str = s.start_time.date().isoformat()
        day_state = db.query(models.DayState).filter(
            models.DayState.athlete_id == athlete_id,
            models.DayState.date == date_str
        ).first()
        
        if not day_state:
            continue
        
        # Get per-lift fatigue
        lift_state = db.query(models.LiftDayState).filter(
            models.LiftDayState.athlete_id == athlete_id,
            models.LiftDayState.date == date_str,
            models.LiftDayState.lift == s.lift
        ).first()
        
        d_l = lift_state.D_l if lift_state else 0
        
        entry = {
            'date': date_str,
            'lift': s.lift.value,
            'session_id': s.id,
            'rpe': session_rpe,
            'd_sys': day_state.D_sys,
            'd_l': d_l,
            't_legs': day_state.T_legs,
            'tonnage': s.tonnage,
            'avg_intensity': s.avg_intensity
        }
        
        rpe_analysis.append(entry)
        rpe_values.append(session_rpe)
        d_sys_values.append(day_state.D_sys)
        d_l_values.append(d_l)
        t_legs_values.append(day_state.T_legs)
        
        # Lift-specific data
        lift_specific[s.lift.value]['rpe'].append(session_rpe)
        lift_specific[s.lift.value]['d_l'].append(d_l)
        lift_specific[s.lift.value]['tonnage'].append(s.tonnage)
    
    if not rpe_analysis:
        print("\n❌ No RPE data found in sessions!")
        return
    
    print(f"\n✓ Found {len(rpe_analysis)} sessions with RPE data")
    print(f"  RPE range: {min(rpe_values):.1f} - {max(rpe_values):.1f}")
    print(f"  Mean RPE: {statistics.mean(rpe_values):.2f}")
    
    # Compute correlations
    print('\n' + '='*70)
    print('CORRELATION ANALYSIS: RPE vs Model Fatigue')
    print('='*70)
    
    corr_d_sys = compute_correlation(rpe_values, d_sys_values)
    corr_d_l = compute_correlation(rpe_values, d_l_values)
    corr_t_legs = compute_correlation(rpe_values, t_legs_values)
    
    print(f"\n{'Metric':<25} {'Correlation':>15} {'Interpretation':>25}")
    print('-'*70)
    
    def interpret_corr(r):
        if r is None:
            return "Insufficient data"
        abs_r = abs(r)
        if abs_r >= 0.7:
            return "Strong" + (" positive" if r > 0 else " negative")
        elif abs_r >= 0.4:
            return "Moderate" + (" positive" if r > 0 else " negative")
        elif abs_r >= 0.2:
            return "Weak" + (" positive" if r > 0 else " negative")
        else:
            return "Negligible"
    
    print(f"{'RPE vs D_sys':<25} {corr_d_sys or 'N/A':>15.3f} {interpret_corr(corr_d_sys):>25}")
    print(f"{'RPE vs D_l (per-lift)':<25} {corr_d_l or 'N/A':>15.3f} {interpret_corr(corr_d_l):>25}")
    print(f"{'RPE vs T_legs':<25} {corr_t_legs or 'N/A':>15.3f} {interpret_corr(corr_t_legs):>25}")
    
    # Per-lift correlation
    print('\n' + '='*70)
    print('PER-LIFT CORRELATION: RPE vs D_l')
    print('='*70)
    
    print(f"{'Lift':<15} {'N':>8} {'RPE vs D_l':>15} {'Interpretation':>25}")
    print('-'*70)
    
    for lift in sorted(lift_specific.keys()):
        data = lift_specific[lift]
        if len(data['rpe']) >= 2:
            corr = compute_correlation(data['rpe'], data['d_l'])
            print(f"{lift:<15} {len(data['rpe']):>8} {corr or 'N/A':>15.3f} {interpret_corr(corr):>25}")
        else:
            print(f"{lift:<15} {len(data['rpe']):>8} {'N/A':>15} {'Insufficient data':>25}")
    
    # RPE distribution analysis
    print('\n' + '='*70)
    print('RPE DISTRIBUTION ANALYSIS')
    print('='*70)
    
    rpe_bins = {
        'Light (RPE 5-6)': [],
        'Moderate (RPE 7)': [],
        'Hard (RPE 8)': [],
        'Max (RPE 9-10)': []
    }
    
    for entry in rpe_analysis:
        rpe = entry['rpe']
        if 5 <= rpe <= 6:
            rpe_bins['Light (RPE 5-6)'].append(entry)
        elif 6.5 <= rpe <= 7.5:
            rpe_bins['Moderate (RPE 7)'].append(entry)
        elif 7.5 < rpe <= 8.5:
            rpe_bins['Hard (RPE 8)'].append(entry)
        elif rpe > 8.5:
            rpe_bins['Max (RPE 9-10)'].append(entry)
    
    print(f"{'RPE Category':<25} {'Count':>8} {'Avg D_sys':>12} {'Avg D_l':>12} {'Avg T_legs':>12}")
    print('-'*70)
    
    for category, entries in rpe_bins.items():
        if entries:
            avg_d_sys = statistics.mean(e['d_sys'] for e in entries)
            avg_d_l = statistics.mean(e['d_l'] for e in entries)
            avg_t_legs = statistics.mean(e['t_legs'] for e in entries)
            print(f"{category:<25} {len(entries):>8} {avg_d_sys:>12.3f} {avg_d_l:>12.3f} {avg_t_legs:>12.3f}")
        else:
            print(f"{category:<25} {0:>8} {'N/A':>12} {'N/A':>12} {'N/A':>12}")
    
    # Validation summary
    print('\n' + '='*70)
    print('VALIDATION SUMMARY')
    print('='*70)
    
    validations = []
    
    # Check 1: Higher RPE should correlate with higher fatigue
    if corr_d_sys and corr_d_sys > 0.3:
        validations.append("✅ PASS: RPE correlates positively with D_sys (as expected)")
    elif corr_d_sys and corr_d_sys > 0:
        validations.append("⚠️  WEAK: RPE-D_sys correlation positive but weak")
    else:
        validations.append("❌ FAIL: RPE does not correlate with D_sys as expected")
    
    # Check 2: Per-lift fatigue should correlate with RPE
    valid_lift_corrs = [compute_correlation(data['rpe'], data['d_l']) 
                        for lift, data in lift_specific.items() 
                        if len(data['rpe']) >= 2]
    
    if valid_lift_corrs and statistics.mean(valid_lift_corrs) > 0.2:
        validations.append("✅ PASS: Per-lift fatigue correlates with RPE")
    else:
        validations.append("⚠️  WEAK: Per-lift RPE correlation weak or inconsistent")
    
    # Check 3: RPE distribution makes sense
    hard_sessions = rpe_bins['Hard (RPE 8)'] + rpe_bins['Max (RPE 9-10)']
    if hard_sessions:
        avg_d_sys_hard = statistics.mean(e['d_sys'] for e in hard_sessions)
        light_sessions = rpe_bins['Light (RPE 5-6)']
        if light_sessions:
            avg_d_sys_light = statistics.mean(e['d_sys'] for e in light_sessions)
            if avg_d_sys_hard > avg_d_sys_light:
                validations.append("✅ PASS: Hard sessions (RPE 8+) have higher D_sys than light sessions")
            else:
                validations.append("❌ FAIL: Hard sessions do not show higher fatigue")
        else:
            validations.append("⚠️  SKIP: No light sessions to compare")
    
    for v in validations:
        print(f"  {v}")
    
    # Save RPE validation results
    rpe_validation = {
        'total_sessions_with_rpe': len(rpe_analysis),
        'rpe_coverage_pct': (len(rpe_analysis) / len(sessions)) * 100 if sessions else 0,
        'correlations': {
            'rpe_vs_d_sys': corr_d_sys,
            'rpe_vs_d_l': corr_d_l,
            'rpe_vs_t_legs': corr_t_legs
        },
        'per_lift_correlations': {
            lift: compute_correlation(data['rpe'], data['d_l']) if len(data['rpe']) >= 2 else None
            for lift, data in lift_specific.items()
        },
        'rpe_distribution': {
            category: {
                'count': len(entries),
                'avg_d_sys': statistics.mean(e['d_sys'] for e in entries) if entries else None,
                'avg_d_l': statistics.mean(e['d_l'] for e in entries) if entries else None
            }
            for category, entries in rpe_bins.items()
        },
        'validation_checks': validations,
        'raw_data': rpe_analysis
    }
    
    with open(artifacts_dir / 'rpe_validation.json', 'w') as f:
        json.dump(rpe_validation, f, indent=2, default=str)
    
    print(f'\n✓ RPE validation saved to: {artifacts_dir}/rpe_validation.json')
    
    # Recommendations
    print('\n' + '='*70)
    print('RECOMMENDATIONS')
    print('='*70)
    
    if corr_d_sys and corr_d_sys < 0.3:
        print("""
1. CORRELATION IS WEAK - Possible causes:
   - RPE recorded at different time points (during vs after session)
   - Individual RPE calibration varies
   - Model fatigue decay rate may need tuning
   
   Suggested fix: Collect RPE at consistent time point (immediately post-set)
""")
    
    if len(rpe_analysis) < len(sessions) * 0.5:
        print(f"""
2. LOW RPE COVERAGE ({rpe_validation['rpe_coverage_pct']:.1f}%)
   - More RPE data would improve validation reliability
   
   Suggested fix: Ensure RPE is recorded for every set in future sessions
""")
    
    print("""
3. FUTURE VALIDATION ENHANCEMENTS:
   - sRPE (session RPE = RPE × duration) for better load quantification
   - Post-session recovery RPE (24h later) for fatigue validation
   - RPE-velocity relationship (if VBT data becomes available)
""")

if __name__ == '__main__':
    main()
