"""
Sprint V2: Realistic Synthetic Dataset Generator v2 for Concurrent Training

Generates synthetic strength and endurance data with:
- Nonlinear load-velocity behavior
- Realistic within-set velocity decay with noise
- Day-to-day readiness variation (global and lift-specific)
- Missingness (20-30% missing velocity data)
- Technical noise (bar-path variability)
- Breakthrough opportunities
- Cross-domain fatigue patterns
"""

import csv
import json
import random
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class AthleteProfile:
    """Base athlete profile for synthetic data generation."""
    squat_1rm: float = 140.0
    bench_1rm: float = 100.0
    deadlift_1rm: float = 180.0
    press_1rm: float = 70.0
    power_clean_1rm: float = 95.0
    
    # Endurance baselines
    ftp_w: float = 250.0  # Functional Threshold Power
    run_threshold_pace: float = 5.0  # min/km
    swim_threshold_pace: float = 2.0  # min/100m


@dataclass
class LiftProfile:
    """Lift-specific profile for velocity modeling."""
    name: str
    v0: float  # Velocity at 0 load (m/s)
    k: float   # Slope factor for load-velocity curve
    v_max: float = 2.5  # Maximum velocity cap
    v_min: float = 0.15  # Minimum velocity floor
    technical_noise_std: float = 0.05  # Bar-path noise
    fatigue_sensitivity: float = 1.0  # How quickly velocity drops


# Lift profiles based on realistic biomechanics
LIFT_PROFILES = {
    'squat': LiftProfile('squat', v0=0.65, k=0.0035, technical_noise_std=0.08, fatigue_sensitivity=1.2),
    'bench': LiftProfile('bench', v0=0.70, k=0.0030, technical_noise_std=0.04, fatigue_sensitivity=0.9),
    'deadlift': LiftProfile('deadlift', v0=0.55, k=0.0032, technical_noise_std=0.07, fatigue_sensitivity=1.1),
    'press': LiftProfile('press', v0=0.60, k=0.0025, technical_noise_std=0.05, fatigue_sensitivity=0.85),
    'power_clean': LiftProfile('power_clean', v0=0.85, k=0.0050, technical_noise_std=0.10, fatigue_sensitivity=1.3),
}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def piecewise_vref(load_pct: float, profile: LiftProfile) -> float:
    """
    Nonlinear load-velocity reference with piecewise behavior.
    
    - Linear in mid-range (40-85%)
    - Curved deviate at high intensity (>85%)
    - Curved deviate at low intensity (<40%)
    """
    if load_pct > 1.0:
        load_pct = 1.0
    if load_pct < 0.0:
        load_pct = 0.0
    
    # Base linear model: v = v0 - k * load_kg
    # Convert load_pct to absolute based on typical 1RM relationship
    # For simplicity, model directly on load_pct
    
    base_v = profile.v0 * (1.0 - load_pct ** 1.1)  # Slight nonlinearity
    
    # High intensity deviation (>85%): faster drop-off
    if load_pct > 0.85:
        penalty = (load_pct - 0.85) * 0.3  # Extra 30% drop at 100%
        base_v *= (1.0 - penalty)
    
    # Low intensity deviation (<40%): flatter curve
    if load_pct < 0.40:
        boost = (0.40 - load_pct) * 0.2  # Less velocity gain at very light loads
        base_v *= (1.0 + boost)
    
    return max(profile.v_min, min(profile.v_max, base_v))


def generate_rep_velocities(
    v_first: float,
    reps: int,
    profile: LiftProfile,
    readiness: float = 1.0,
    is_breakthrough: bool = False
) -> List[float]:
    """
    Generate per-rep velocities with realistic decay patterns.
    
    Features:
    - Occasional early potentiation (rep 1 slower than rep 2)
    - Catastrophe near failure / high VL
    - Technical noise
    """
    velocities = []
    
    # Base decay rate depends on rep count and fatigue sensitivity
    decay_rate = 0.03 * profile.fatigue_sensitivity
    
    # Breakthrough session: better velocities
    if is_breakthrough:
        readiness *= 1.08  # 8% better performance
    
    for rep in range(reps):
        # Expected velocity for this rep
        expected_v = v_first * math.exp(-decay_rate * rep)
        
        # Add technical noise
        noise = random.gauss(0, profile.technical_noise_std)
        v = expected_v * readiness + noise
        
        # Occasional early potentiation (5% chance, rep 1 only)
        if rep == 0 and random.random() < 0.05:
            v *= 0.95  # Slightly slower first rep
        
        # Catastrophe if very fatigued (VL > 0.30)
        vl_so_far = 1.0 - (v / v_first) if v_first > 0 else 0
        if vl_so_far > 0.30 and random.random() < 0.15:
            v *= 0.85  # Sudden drop
        
        velocities.append(max(0.10, min(profile.v_max, v)))
    
    return velocities


def calculate_vl(velocities: List[float]) -> float:
    """Calculate velocity loss from first to last rep."""
    if len(velocities) < 2:
        return 0.0
    return 1.0 - (velocities[-1] / velocities[0])


def generate_readiness_variation(day: int) -> Dict[str, float]:
    """
    Generate day-to-day readiness variations.
    
    Returns global and lift-specific readiness factors.
    """
    # Global readiness: mostly good, occasional bad days
    global_readiness = 1.0
    if random.random() < 0.15:  # 15% bad days
        global_readiness = random.uniform(0.88, 0.96)
    elif random.random() < 0.10:  # 10% great days
        global_readiness = random.uniform(1.03, 1.08)
    
    # Lift-specific variations (can be different from global)
    lift_readiness = {}
    for lift in LIFT_PROFILES.keys():
        # Most lifts follow global, but some have independent variation
        if random.random() < 0.20:  # 20% chance of lift-specific deviation
            deviation = random.uniform(-0.06, 0.06)
            lift_readiness[lift] = max(0.85, min(1.10, global_readiness + deviation))
        else:
            lift_readiness[lift] = global_readiness
    
    return lift_readiness


# ============================================================================
# STRENGTH DATASET GENERATOR
# ============================================================================

def generate_strength_session(
    session_date: datetime,
    session_id: str,
    session_label: str,
    lift: str,
    profile: LiftProfile,
    athlete: AthleteProfile,
    readiness: float,
    session_type: str = 'strength',  # 'strength', 'volume', 'power'
    is_deload: bool = False,
    is_breakthrough: bool = False
) -> List[Dict]:
    """Generate a single strength session with multiple sets."""
    
    sets = []
    
    # Get 1RM for this lift
    rm_map = {
        'squat': athlete.squat_1rm,
        'bench': athlete.bench_1rm,
        'deadlift': athlete.deadlift_1rm,
        'press': athlete.press_1rm,
        'power_clean': athlete.power_clean_1rm,
    }
    rm_1rm = rm_map.get(lift, 100.0)
    
    # Adjust load based on session type
    if session_type == 'strength':
        base_intensity = random.uniform(0.82, 0.92)
        base_reps = random.choice([2, 3, 4])
        num_sets = random.randint(3, 5)
    elif session_type == 'volume':
        base_intensity = random.uniform(0.70, 0.80)
        base_reps = random.choice([6, 8, 10])
        num_sets = random.randint(3, 5)
    else:  # power
        base_intensity = random.uniform(0.60, 0.75)
        base_reps = random.choice([1, 2, 3])
        num_sets = random.randint(4, 6)
    
    # Deload adjustment
    if is_deload:
        base_intensity *= 0.85
        base_reps = max(2, base_reps - 1)
        num_sets = max(2, num_sets - 1)
    
    # Round load to nearest 2.5kg
    load_kg = round((rm_1rm * base_intensity) / 2.5) * 2.5
    
    # Generate sets
    rest_sec = 180 if session_type == 'strength' else (120 if session_type == 'power' else 150)
    
    for set_idx in range(1, num_sets + 1):
        # Fatigue accumulation across sets
        set_fatigue = 1.0 - (0.03 * (set_idx - 1))
        
        # Slight rep reduction on later sets
        reps = base_reps
        if set_idx > 3 and random.random() < 0.3:
            reps = max(1, base_reps - 1)
        
        # Calculate reference velocity for this load
        load_pct = load_kg / rm_1rm
        v_ref = piecewise_vref(load_pct, profile)
        v_first = v_ref * readiness * set_fatigue
        
        # Generate velocities
        velocities = generate_rep_velocities(v_first, reps, profile, readiness, is_breakthrough)
        
        # Calculate RPE based on VL and subjective feel
        vl = calculate_vl(velocities)
        base_rpe = 6.5 + (vl * 4.0)  # VL 0.0 -> RPE 6.5, VL 0.5 -> RPE 8.5
        rpe = min(10.0, max(5.0, base_rpe + random.gauss(0, 0.3)))
        
        # Missingness: 25% chance of no velocity data
        has_velocity = random.random() > 0.25
        
        # Missing rest_sec occasionally (10%)
        set_rest = rest_sec if random.random() > 0.10 else None
        
        sets.append({
            'session_date': session_date.strftime('%Y-%m-%d'),
            'session_id': session_id,
            'session_label': session_label,
            'lift_code': lift,
            'set_index': set_idx,
            'load_kg': load_kg,
            'reps': reps,
            'rest_sec': set_rest,
            'rpe': round(rpe, 1),
            'velocities': json.dumps(velocities) if has_velocity else None,
            '_vl': vl,  # Internal for debugging
            '_has_velocity': has_velocity,
        })
    
    return sets


def generate_strength_dataset_v2(
    output_path: str = '/mnt/data/strength_log_vbt_synthetic_v2.csv',
    athlete_id: int = 299
) -> str:
    """Generate realistic synthetic strength dataset v2."""
    
    athlete = AthleteProfile()
    
    # 12 weeks program
    start_date = datetime(2026, 1, 1)
    weeks = 12
    sessions_per_week = 3
    
    all_sets = []
    session_counter = 1
    
    lifts = ['squat', 'bench', 'deadlift', 'press', 'power_clean']
    
    for week in range(weeks):
        # Simple 4-week wave: 3 weeks up, 1 week deload
        is_deload_week = (week + 1) % 4 == 0
        
        for session_in_week in range(sessions_per_week):
            session_date = start_date + timedelta(weeks=week, days=session_in_week * 2)
            session_id = f"S{session_counter:03d}"
            session_label = f"W{week+1}-{chr(ord('A') + session_in_week)}"
            
            # Generate readiness for this day
            readiness_map = generate_readiness_variation(week * 7 + session_in_week)
            
            # Occasionally breakthrough session (5% chance, not on deload)
            is_breakthrough = random.random() < 0.05 and not is_deload_week
            
            # Pick 2-3 lifts per session
            session_lifts = random.sample(lifts, k=random.randint(2, 3))
            
            for lift in session_lifts:
                profile = LIFT_PROFILES[lift]
                readiness = readiness_map.get(lift, 1.0)
                
                # Session type based on lift and position
                if lift in ['squat', 'deadlift'] and not is_deload_week:
                    session_type = random.choice(['strength', 'volume'])
                elif lift == 'power_clean':
                    session_type = 'power'
                else:
                    session_type = random.choice(['strength', 'volume', 'power'])
                
                sets = generate_strength_session(
                    session_date=session_date,
                    session_id=session_id,
                    session_label=session_label,
                    lift=lift,
                    profile=profile,
                    athlete=athlete,
                    readiness=readiness,
                    session_type=session_type,
                    is_deload=is_deload_week,
                    is_breakthrough=is_breakthrough
                )
                all_sets.extend(sets)
            
            session_counter += 1
    
    # Write to CSV
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'session_date', 'session_id', 'session_label', 'lift_code',
            'set_index', 'load_kg', 'reps', 'rest_sec', 'rpe', 'velocities'
        ])
        writer.writeheader()
        for s in all_sets:
            writer.writerow({
                'session_date': s['session_date'],
                'session_id': s['session_id'],
                'session_label': s['session_label'],
                'lift_code': s['lift_code'],
                'set_index': s['set_index'],
                'load_kg': s['load_kg'],
                'reps': s['reps'],
                'rest_sec': s['rest_sec'],
                'rpe': s['rpe'],
                'velocities': s['velocities'],
            })
    
    # Stats
    total_sets = len(all_sets)
    sets_with_velocity = sum(1 for s in all_sets if s['_has_velocity'])
    breakthrough_sessions = sum(1 for s in all_sets if s.get('_is_breakthrough', False))
    
    print(f"Generated strength dataset v2: {output_path}")
    print(f"  Total sets: {total_sets}")
    print(f"  Sets with velocity: {sets_with_velocity} ({100*sets_with_velocity/total_sets:.1f}%)")
    print(f"  Missing velocity: {total_sets - sets_with_velocity} ({100*(total_sets-sets_with_velocity)/total_sets:.1f}%)")
    
    return output_path


# ============================================================================
# ENDURANCE DATASET GENERATOR
# ============================================================================

def generate_endurance_session(
    session_date: datetime,
    session_id: str,
    sport: str,
    athlete: AthleteProfile,
    session_type: str = 'z2',  # 'z2', 'tempo', 'hiit', 'long'
    is_fatigued: bool = False
) -> Dict:
    """Generate a single endurance session."""
    
    # Base values by sport and session type
    if sport == 'cycling':
        base_duration = {
            'z2': 75, 'tempo': 60, 'hiit': 45, 'long': 150
        }.get(session_type, 60)
        
        base_ftp_pct = {
            'z2': 0.65, 'tempo': 0.88, 'hiit': 1.05, 'long': 0.60
        }.get(session_type, 0.65)
        
        is_hiit = session_type == 'hiit'
        
    elif sport == 'running':
        base_duration = {
            'z2': 45, 'tempo': 35, 'hiit': 30, 'long': 90
        }.get(session_type, 45)
        base_ftp_pct = None  # No power for running
        is_hiit = session_type == 'hiit'
        
    else:  # swimming
        base_duration = {
            'z2': 40, 'tempo': 30, 'hiit': 25, 'long': 60
        }.get(session_type, 40)
        base_ftp_pct = None
        is_hiit = session_type == 'hiit'
    
    # Fatigue adjustment
    if is_fatigued:
        base_duration = int(base_duration * 0.85)
        base_ftp_pct = base_ftp_pct * 0.92 if base_ftp_pct else None
    
    # Add duration noise
    duration = int(base_duration * random.uniform(0.90, 1.10))
    
    # Generate power metrics for cycling
    if sport == 'cycling' and base_ftp_pct:
        target_w = athlete.ftp_w * base_ftp_pct
        
        # Add noise to power
        avg_w = target_w * random.uniform(0.95, 1.05)
        np_w = avg_w * random.uniform(1.02, 1.08) if is_hiit else avg_w * random.uniform(0.98, 1.02)
        
        # Best efforts (noisy)
        best_20min_w = athlete.ftp_w * random.uniform(0.98, 1.08) if not is_fatigued else athlete.ftp_w * random.uniform(0.90, 1.00)
        best_5min_w = athlete.ftp_w * random.uniform(1.10, 1.25) if not is_fatigued else athlete.ftp_w * random.uniform(1.05, 1.15)
        
        # TSS estimate
        tss = (duration / 60) * (avg_w / athlete.ftp_w) ** 2 * 100
        if is_hiit:
            tss *= 1.3
    else:
        avg_w = np_w = best_20min_w = best_5min_w = None
        tss = duration * (0.7 if session_type == 'z2' else 1.0 if session_type == 'tempo' else 1.3)
    
    # Intensity JSON
    intensity_json = json.dumps({
        'avg_w': avg_w,
        'best_20min_w': best_20min_w,
        'best_5min_w': best_5min_w,
        'intent': session_type,
        'is_HIIT': is_hiit,
        'np_w': np_w,
        'tss': round(tss, 1),
    })
    
    return {
        'session_date': session_date.strftime('%Y-%m-%d'),
        'session_id': session_id,
        'sport': sport,
        'duration_min': duration,
        'is_HIIT': 1 if is_hiit else 0,
        'tss': round(tss, 1),
        'best_20min_w': best_20min_w,
        'best_5min_w': best_5min_w,
        'np_w': np_w,
        'avg_w': avg_w,
        'intensity_json': intensity_json,
    }


def generate_endurance_dataset_v2(
    output_path: str = '/mnt/data/endurance_log_synthetic_v2.csv',
    athlete_id: int = 299
) -> str:
    """Generate realistic synthetic endurance dataset v2."""
    
    athlete = AthleteProfile()
    
    # 12 weeks
    start_date = datetime(2026, 1, 1)
    weeks = 12
    sessions_per_week = 4
    
    all_sessions = []
    session_counter = 1
    
    sports = ['cycling', 'running', 'swimming']
    session_types = ['z2', 'tempo', 'hiit', 'long']
    
    for week in range(weeks):
        for session_in_week in range(sessions_per_week):
            session_date = start_date + timedelta(weeks=week, days=session_in_week * 2 + 1)
            session_id = f"E{session_counter:03d}"
            
            # Pick sport with cycling bias
            sport = random.choices(
                sports, 
                weights=[0.5, 0.35, 0.15]
            )[0]
            
            # Pick session type with periodization
            if (week + 1) % 4 == 0:  # Deload week
                session_type = random.choice(['z2', 'long'])
            elif session_in_week == 0:
                session_type = random.choice(['hiit', 'tempo'])
            elif session_in_week == 2:
                session_type = random.choice(['long', 'z2'])
            else:
                session_type = random.choice(['z2', 'tempo'])
            
            # Fatigue occasionally (10% of sessions)
            is_fatigued = random.random() < 0.10
            
            session = generate_endurance_session(
                session_date=session_date,
                session_id=session_id,
                sport=sport,
                athlete=athlete,
                session_type=session_type,
                is_fatigued=is_fatigued
            )
            all_sessions.append(session)
            session_counter += 1
    
    # Write to CSV
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'session_date', 'session_id', 'sport', 'duration_min', 'is_HIIT',
            'tss', 'best_20min_w', 'best_5min_w', 'np_w', 'avg_w', 'intensity_json'
        ])
        writer.writeheader()
        writer.writerows(all_sessions)
    
    # Stats
    total = len(all_sessions)
    cycling = sum(1 for s in all_sessions if s['sport'] == 'cycling')
    running = sum(1 for s in all_sessions if s['sport'] == 'running')
    swimming = sum(1 for s in all_sessions if s['sport'] == 'swimming')
    hiit = sum(1 for s in all_sessions if s['is_HIIT'] == 1)
    
    print(f"\nGenerated endurance dataset v2: {output_path}")
    print(f"  Total sessions: {total}")
    print(f"  Cycling: {cycling}, Running: {running}, Swimming: {swimming}")
    print(f"  HIIT sessions: {hiit}")
    
    return output_path


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Synthetic Dataset Generator v2")
    print("=" * 60)
    
    # Set seed for reproducibility (but can be changed)
    random.seed(42)
    
    # Generate strength dataset
    strength_path = generate_strength_dataset_v2()
    
    # Generate endurance dataset
    endurance_path = generate_endurance_dataset_v2()
    
    print("\n" + "=" * 60)
    print("Dataset generation complete!")
    print("=" * 60)
    print(f"\nFiles generated:")
    print(f"  1. {strength_path}")
    print(f"  2. {endurance_path}")
    print("\nNext steps:")
    print("  - Import to database")
    print("  - Run replay/validate")
    print("  - Compare with v1 synthetic assumptions")
