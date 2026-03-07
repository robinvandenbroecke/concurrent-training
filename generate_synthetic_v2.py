"""
Sprint V2-Enhanced: Realistic Synthetic Dataset Generator v2

Generates synthetic strength and endurance data with deliberate interference patterns,
concurrent training stressors, and model-mismatch elements for stress-testing.
"""

import csv
import json
import random
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import statistics


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
    ftp_w: float = 250.0
    run_threshold_pace: float = 5.0
    swim_threshold_pace: float = 2.0


@dataclass
class LiftProfile:
    """Lift-specific profile for velocity modeling."""
    name: str
    v0: float
    k: float
    v_max: float = 2.5
    v_min: float = 0.15
    technical_noise_std: float = 0.05
    fatigue_sensitivity: float = 1.0


# Lift profiles with realistic parameters
LIFT_PROFILES = {
    'squat': LiftProfile('squat', v0=0.65, k=0.0035, technical_noise_std=0.08, fatigue_sensitivity=1.2),
    'bench': LiftProfile('bench', v0=0.70, k=0.0030, technical_noise_std=0.04, fatigue_sensitivity=0.9),
    'deadlift': LiftProfile('deadlift', v0=0.55, k=0.0032, technical_noise_std=0.07, fatigue_sensitivity=1.1),
    'press': LiftProfile('press', v0=0.60, k=0.0025, technical_noise_std=0.05, fatigue_sensitivity=0.85),
    'power_clean': LiftProfile('power_clean', v0=0.85, k=0.0050, technical_noise_std=0.10, fatigue_sensitivity=1.3),
}


# ============================================================================
# INTERFERENCE & FATIGUE MODELING
# ============================================================================

class InterferenceModel:
    """Models concurrent training interference patterns."""
    
    def __init__(self):
        self.interference_matrix = {
            ('squat', 'hiit'): 0.35, ('squat', 'tempo'): 0.25, ('squat', 'z2'): 0.10, ('squat', 'long'): 0.15,
            ('deadlift', 'hiit'): 0.40, ('deadlift', 'tempo'): 0.30, ('deadlift', 'z2'): 0.12, ('deadlift', 'long'): 0.18,
            ('power_clean', 'hiit'): 0.30, ('power_clean', 'tempo'): 0.20, ('power_clean', 'z2'): 0.08, ('power_clean', 'long'): 0.12,
            ('bench', 'hiit'): 0.15, ('bench', 'tempo'): 0.10, ('bench', 'z2'): 0.03, ('bench', 'long'): 0.05,
            ('press', 'hiit'): 0.12, ('press', 'tempo'): 0.08, ('press', 'z2'): 0.02, ('press', 'long'): 0.04,
        }
        self.recovery_halflife = 2.5
    
    def compute_fatigue(self, lift: str, endurance_sessions: List[Dict], target_date: datetime) -> float:
        """Compute accumulated fatigue for a lift based on recent endurance sessions."""
        total_interference = 0.0
        for session in endurance_sessions:
            days_ago = (target_date - session['date']).days
            if days_ago < 0 or days_ago > 7:
                continue
            session_type = session['type']
            key = (lift, session_type)
            base_interference = self.interference_matrix.get(key, 0.1)
            intensity_factor = session.get('tss', 50) / 100
            decay = math.exp(-days_ago / self.recovery_halflife)
            total_interference += base_interference * intensity_factor * decay
        return max(0.75, 1.0 - total_interference)


# ============================================================================
# PERIODIZATION & STRESS MODELING
# ============================================================================

class PeriodizationModel:
    """12-week periodization with intentional interference weeks and deloads."""
    
    def __init__(self):
        self.weeks = [
            # Base building (moderate stress)
            {'week': 1, 'phase': 'base', 'stress_level': 'moderate', 'interference_pattern': 'minimal'},
            {'week': 2, 'phase': 'base', 'stress_level': 'moderate', 'interference_pattern': 'minimal'},
            {'week': 3, 'phase': 'base', 'stress_level': 'moderate', 'interference_pattern': 'minimal'},
            # Deload (recovery)
            {'week': 4, 'phase': 'deload', 'stress_level': 'low', 'interference_pattern': 'none'},
            # Build 2 (higher stress, introduction of HIIT)
            {'week': 5, 'phase': 'build_2', 'stress_level': 'high', 'interference_pattern': 'minimal'},
            {'week': 6, 'phase': 'build_2', 'stress_level': 'high', 'interference_pattern': 'minimal'},
            {'week': 7, 'phase': 'build_2', 'stress_level': 'high', 'interference_pattern': 'moderate'},
            # HIGH INTERFERENCE WEEK (heavy lower + HIIT clustered)
            {'week': 8, 'phase': 'interference_test', 'stress_level': 'very_high', 'interference_pattern': 'maximal'},
            # Recovery (rebound expected)
            {'week': 9, 'phase': 'recovery', 'stress_level': 'low', 'interference_pattern': 'none'},
            # Peak (performance rebound)
            {'week': 10, 'phase': 'peak', 'stress_level': 'moderate', 'interference_pattern': 'minimal'},
            {'week': 11, 'phase': 'peak', 'stress_level': 'moderate', 'interference_pattern': 'minimal'},
            # Taper (final peak test)
            {'week': 12, 'phase': 'taper', 'stress_level': 'very_low', 'interference_pattern': 'none'},
        ]
    
    def get_week_config(self, week_num: int) -> Dict:
        for w in self.weeks:
            if w['week'] == week_num:
                return w
        return self.weeks[0]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def piecewise_vref(load_pct: float, profile: LiftProfile) -> float:
    """Nonlinear load-velocity with INTENTIONAL MODEL MISMATCH."""
    if load_pct > 1.0:
        load_pct = 1.0
    if load_pct < 0.0:
        load_pct = 0.0
    
    # Slightly different exponent than model assumes
    base_v = profile.v0 * (1.0 - load_pct ** 1.15)
    
    if load_pct > 0.85:
        penalty = (load_pct - 0.85) * 0.35
        base_v *= (1.0 - penalty)
    
    if load_pct < 0.40:
        boost = (0.40 - load_pct) * 0.25
        base_v *= (1.0 + boost)
    
    return max(profile.v_min, min(profile.v_max, base_v))


def generate_rep_velocities(v_first: float, reps: int, profile: LiftProfile,
                           readiness: float = 1.0, is_breakthrough: bool = False,
                           accumulated_fatigue: float = 1.0) -> List[float]:
    """Generate velocities with model-mismatch elements."""
    velocities = []
    decay_rate = 0.032 * profile.fatigue_sensitivity  # Slightly different from 0.03
    effective_readiness = readiness * accumulated_fatigue
    
    if is_breakthrough:
        effective_readiness *= 1.10
    
    for rep in range(reps):
        expected_v = v_first * math.exp(-decay_rate * rep)
        noise_std = profile.technical_noise_std * (1.0 + 0.1 * rep)
        noise = random.gauss(0, noise_std)
        v = expected_v * effective_readiness + noise
        
        if rep == 0 and random.random() < 0.08:
            v *= 0.93
        
        vl_so_far = 1.0 - (v / v_first) if v_first > 0 else 0
        if vl_so_far > 0.35 and random.random() < 0.20:
            v *= 0.82
        
        velocities.append(max(0.10, min(profile.v_max, v)))
    
    return velocities


def calculate_vl(velocities: List[float]) -> float:
    if len(velocities) < 2:
        return 0.0
    return 1.0 - (velocities[-1] / velocities[0])


def generate_readiness_variation(day: int, week_config: Dict) -> Dict[str, float]:
    """Generate ASYMMETRIC bad days - some lifts off, others normal."""
    lifts = list(LIFT_PROFILES.keys())
    phase = week_config['phase']
    
    if phase in ['deload', 'recovery', 'taper']:
        global_readiness = random.uniform(0.98, 1.08)
    elif phase == 'interference_test':
        global_readiness = random.uniform(0.88, 0.95)
    else:
        if random.random() < 0.18:
            global_readiness = random.uniform(0.86, 0.95)
        elif random.random() < 0.12:
            global_readiness = random.uniform(1.04, 1.12)
        else:
            global_readiness = 1.0
    
    lift_readiness = {}
    for lift in lifts:
        # 30% chance of lift-specific deviation
        if random.random() < 0.30:
            deviation = random.uniform(-0.08, 0.08)
            lift_readiness[lift] = max(0.82, min(1.15, global_readiness + deviation))
        else:
            lift_readiness[lift] = global_readiness
    
    return lift_readiness


# ============================================================================
# STRENGTH DATASET GENERATOR
# ============================================================================

def generate_strength_session(session_date: datetime, session_id: str, session_label: str,
                               lift: str, profile: LiftProfile, athlete: AthleteProfile,
                               readiness: float, week_config: Dict, session_type: str = 'strength',
                               accumulated_fatigue: float = 1.0, is_breakthrough: bool = False) -> List[Dict]:
    """Generate strength session with interference-aware parameters."""
    sets = []
    rm_map = {'squat': athlete.squat_1rm, 'bench': athlete.bench_1rm, 'deadlift': athlete.deadlift_1rm,
              'press': athlete.press_1rm, 'power_clean': athlete.power_clean_1rm}
    rm_1rm = rm_map.get(lift, 100.0)
    phase = week_config['phase']
    
    if phase == 'deload':
        base_intensity, base_reps, num_sets = random.uniform(0.70, 0.78), random.choice([3, 4, 5]), random.randint(2, 3)
    elif phase == 'interference_test' and lift in ['squat', 'deadlift']:
        base_intensity, base_reps, num_sets = random.uniform(0.88, 0.95), random.choice([1, 2, 3]), random.randint(4, 5)
    elif phase == 'taper':
        base_intensity, base_reps, num_sets = random.uniform(0.90, 0.98), random.choice([1, 2]), random.randint(2, 3)
    elif session_type == 'strength':
        base_intensity, base_reps, num_sets = random.uniform(0.82, 0.92), random.choice([2, 3, 4]), random.randint(3, 5)
    elif session_type == 'volume':
        base_intensity, base_reps, num_sets = random.uniform(0.70, 0.80), random.choice([6, 8, 10]), random.randint(3, 5)
    else:
        base_intensity, base_reps, num_sets = random.uniform(0.60, 0.75), random.choice([1, 2, 3]), random.randint(4, 6)
    
    load_kg = round((rm_1rm * base_intensity) / 2.5) * 2.5
    rest_sec = 180 if session_type == 'strength' else (120 if session_type == 'power' else 150)
    
    for set_idx in range(1, num_sets + 1):
        set_fatigue = 1.0 - (0.025 * (set_idx - 1))
        reps = base_reps
        if set_idx > 3 and random.random() < 0.35:
            reps = max(1, base_reps - 1)
        
        load_pct = load_kg / rm_1rm
        v_ref = piecewise_vref(load_pct, profile)
        v_first = v_ref * readiness * set_fatigue
        
        velocities = generate_rep_velocities(v_first, reps, profile, readiness, is_breakthrough, accumulated_fatigue)
        vl = calculate_vl(velocities)
        base_rpe = 6.0 + (vl * 4.5)
        rpe = min(10.0, max(5.0, base_rpe + random.gauss(0, 0.4)))
        
        has_velocity = random.random() > 0.28
        set_rest = rest_sec if random.random() > 0.12 else None
        set_rpe = round(rpe, 1) if random.random() > 0.08 else None
        
        sets.append({
            'session_date': session_date.strftime('%Y-%m-%d'), 'session_id': session_id,
            'session_label': session_label, 'lift_code': lift, 'set_index': set_idx,
            'load_kg': load_kg, 'reps': reps, 'rest_sec': set_rest, 'rpe': set_rpe,
            'velocities': json.dumps(velocities) if has_velocity else None,
            '_vl': vl, '_has_velocity': has_velocity,
        })
    
    return sets


def generate_strength_dataset_v2(output_path: str = '/mnt/data/strength_log_vbt_synthetic_v2.csv',
                                  athlete_id: int = 299) -> Tuple[str, List[Dict]]:
    """Generate strength dataset with interference modeling."""
    athlete = AthleteProfile()
    periodization = PeriodizationModel()
    start_date = datetime(2026, 1, 1)
    weeks, sessions_per_week = 12, 3
    all_sets, session_counter = [], 1
    endurance_log = []
    lifts = ['squat', 'bench', 'deadlift', 'press', 'power_clean']
    
    for week in range(weeks):
        week_num = week + 1
        week_config = periodization.get_week_config(week_num)
        
        for session_in_week in range(sessions_per_week):
            session_date = start_date + timedelta(weeks=week, days=session_in_week * 2)
            session_id = f"S{session_counter:03d}"
            session_label = f"W{week_num}-{chr(ord('A') + session_in_week)}"
            
            readiness_map = generate_readiness_variation(week * 7 + session_in_week, week_config)
            is_breakthrough = (week_config['phase'] in ['peak', 'taper'] and random.random() < 0.15) or (random.random() < 0.05)
            
            if week_config['phase'] == 'interference_test':
                session_lifts = random.sample(['squat', 'deadlift'], k=2)
                if random.random() < 0.5:
                    session_lifts.append(random.choice(['bench', 'press']))
            else:
                session_lifts = random.sample(lifts, k=random.randint(2, 3))
            
            for lift in session_lifts:
                profile = LIFT_PROFILES[lift]
                readiness = readiness_map.get(lift, 1.0)
                interference = InterferenceModel()
                recent_endurance = [e for e in endurance_log if 0 <= (session_date - e['date']).days <= 3]
                accumulated_fatigue = interference.compute_fatigue(lift, recent_endurance, session_date)
                
                if week_config['phase'] in ['deload', 'recovery']:
                    session_type = 'recovery'
                elif lift in ['squat', 'deadlift'] and week_config['phase'] not in ['deload']:
                    session_type = random.choice(['strength', 'volume'])
                elif lift == 'power_clean':
                    session_type = 'power'
                else:
                    session_type = random.choice(['strength', 'volume'])
                
                sets = generate_strength_session(session_date, session_id, session_label, lift, profile,
                                                  athlete, readiness, week_config, session_type,
                                                  accumulated_fatigue, is_breakthrough)
                all_sets.extend(sets)
            
            session_counter += 1
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['session_date', 'session_id', 'session_label', 'lift_code',
                                                'set_index', 'load_kg', 'reps', 'rest_sec', 'rpe', 'velocities'])
        writer.writeheader()
        for s in all_sets:
            writer.writerow({k: s[k] for k in ['session_date', 'session_id', 'session_label', 'lift_code',
                                                'set_index', 'load_kg', 'reps', 'rest_sec', 'rpe', 'velocities']})
    
    total_sets = len(all_sets)
    sets_with_velocity = sum(1 for s in all_sets if s['_has_velocity'])
    print(f"Generated strength dataset v2: {output_path}")
    print(f"  Total sets: {total_sets}")
    print(f"  Sets with velocity: {sets_with_velocity} ({100*sets_with_velocity/total_sets:.1f}%)")
    
    return output_path, endurance_log


# ============================================================================
# ENDURANCE DATASET GENERATOR
# ============================================================================

def generate_endurance_session(session_date: datetime, session_id: str, sport: str,
                                athlete: AthleteProfile, week_config: Dict,
                                session_type: str = 'z2') -> Tuple[Dict, Dict]:
    """Generate endurance session with interference pattern awareness."""
    phase = week_config['phase']
    
    if sport == 'cycling':
        base_duration = {'z2': 75, 'tempo': 60, 'hiit': 45, 'long': 150}.get(session_type, 60)
        base_ftp_pct = {'z2': 0.65, 'tempo': 0.88, 'hiit': 1.05, 'long': 0.60}.get(session_type, 0.65)
        is_hiit = session_type == 'hiit'
    elif sport == 'running':
        base_duration = {'z2': 45, 'tempo': 35, 'hiit': 30, 'long': 90}.get(session_type, 45)
        base_ftp_pct, is_hiit = None, session_type == 'hiit'
    else:
        base_duration = {'z2': 40, 'tempo': 30, 'hiit': 25, 'long': 60}.get(session_type, 40)
        base_ftp_pct, is_hiit = None, session_type == 'hiit'
    
    if phase in ['deload', 'taper']:
        base_duration = int(base_duration * 0.60)
        if base_ftp_pct:
            base_ftp_pct *= 0.90
    elif phase == 'recovery':
        base_duration = int(base_duration * 0.75)
    
    duration = int(base_duration * random.uniform(0.88, 1.12))
    
    if sport == 'cycling' and base_ftp_pct:
        target_w = athlete.ftp_w * base_ftp_pct
        if phase == 'interference_test':
            target_w *= 0.92
        avg_w = target_w * random.uniform(0.93, 1.07)
        np_w = avg_w * random.uniform(1.02, 1.10) if is_hiit else avg_w * random.uniform(0.97, 1.03)
        best_20min_w = athlete.ftp_w * random.uniform(0.95, 1.05)
        best_5min_w = athlete.ftp_w * random.uniform(1.08, 1.22)
        tss = (duration / 60) * (avg_w / athlete.ftp_w) ** 2 * 100
        if is_hiit:
            tss *= 1.35
    else:
        avg_w = np_w = best_20min_w = best_5min_w = None
        tss = duration * (0.65 if session_type == 'z2' else 0.95 if session_type == 'tempo' else 1.4)
    
    tss = min(tss, 200)
    
    intensity_json = json.dumps({'avg_w': avg_w, 'best_20min_w': best_20min_w, 'best_5min_w': best_5min_w,
                                  'intent': session_type, 'is_HIIT': is_hiit, 'np_w': np_w, 'tss': round(tss, 1)})
    
    session_data = {'session_date': session_date.strftime('%Y-%m-%d'), 'session_id': session_id, 'sport': sport,
                    'duration_min': duration, 'is_HIIT': 1 if is_hiit else 0, 'tss': round(tss, 1),
                    'best_20min_w': best_20min_w, 'best_5min_w': best_5min_w, 'np_w': np_w, 'avg_w': avg_w,
                    'intensity_json': intensity_json}
    
    interference_record = {'date': session_date, 'sport': sport, 'type': session_type, 'tss': tss, 'is_hiit': is_hiit}
    
    return session_data, interference_record


def generate_endurance_dataset_v2(output_path: str = '/mnt/data/endurance_log_synthetic_v2.csv',
                                   athlete_id: int = 299) -> Tuple[str, List[Dict]]:
    """Generate endurance dataset with deliberate interference patterns."""
    athlete = AthleteProfile()
    periodization = PeriodizationModel()
    start_date = datetime(2026, 1, 1)
    weeks = 12
    all_sessions, interference_log, session_counter = [], [], 1
    sports = ['cycling', 'running', 'swimming']
    
    for week in range(weeks):
        week_num = week + 1
        week_config = periodization.get_week_config(week_num)
        
        if week_config['phase'] in ['deload', 'taper']:
            sessions_this_week = 2
        elif week_config['phase'] == 'interference_test':
            sessions_this_week = 4
        else:
            sessions_this_week = 4
        
        for session_in_week in range(sessions_this_week):
            session_date = start_date + timedelta(weeks=week, days=session_in_week * 2 + 1)
            session_id = f"E{session_counter:03d}"
            
            if week_config['phase'] == 'interference_test':
                sport = random.choices(['cycling', 'running'], weights=[0.7, 0.3])[0]
            else:
                sport = random.choices(sports, weights=[0.50, 0.35, 0.15])[0]
            
            if week_config['phase'] == 'deload':
                session_type = 'z2'
            elif week_config['phase'] == 'taper':
                session_type = random.choice(['z2', 'tempo'])
            elif week_config['phase'] == 'interference_test':
                session_type = 'hiit' if session_in_week in [0, 2] else random.choice(['z2', 'tempo'])
            elif week_config['phase'] in ['build_2', 'peak']:
                session_type = random.choice(['z2', 'tempo', 'hiit', 'long'])
            elif session_in_week == 0:
                session_type = random.choice(['hiit', 'tempo'])
            elif session_in_week == 2:
                session_type = random.choice(['long', 'z2'])
            else:
                session_type = random.choice(['z2', 'tempo'])
            
            session, interference = generate_endurance_session(session_date, session_id, sport, athlete, week_config, session_type)
            all_sessions.append(session)
            interference_log.append(interference)
            session_counter += 1
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['session_date', 'session_id', 'sport', 'duration_min', 'is_HIIT',
                                                'tss', 'best_20min_w', 'best_5min_w', 'np_w', 'avg_w', 'intensity_json'])
        writer.writeheader()
        writer.writerows(all_sessions)
    
    total = len(all_sessions)
    cycling = sum(1 for s in all_sessions if s['sport'] == 'cycling')
    running = sum(1 for s in all_sessions if s['sport'] == 'running')
    swimming = sum(1 for s in all_sessions if s['sport'] == 'swimming')
    hiit = sum(1 for s in all_sessions if s['is_HIIT'] == 1)
    
    print(f"\nGenerated endurance dataset v2: {output_path}")
    print(f"  Total sessions: {total}")
    print(f"  Cycling: {cycling}, Running: {running}, Swimming: {swimming}")
    print(f"  HIIT sessions: {hiit}")
    
    return output_path, interference_log


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Synthetic Dataset Generator v2 - Enhanced")
    print("=" * 60)
    
    random.seed(42)
    
    strength_path, _ = generate_strength_dataset_v2()
    endurance_path, _ = generate_endurance_dataset_v2()
    
    print("\n" + "=" * 60)
    print("Dataset generation complete!")
    print("=" * 60)
