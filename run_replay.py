#!/usr/bin/env python3
"""
Replay and validation runner for strength data.
"""
import json
import csv
from datetime import date
from pathlib import Path
from collections import defaultdict
import statistics

import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from app.database import SessionLocal
from app import models
from app.eval.replay import ReplayRunner
from app.services.engine_orchestrator import EngineOrchestrator
from app.domain.day_engine import PerLiftState

def main():
    db = SessionLocal()
    athlete_id = 1
    
    artifacts_dir = Path('./artifacts/eval_strength_2026_01')
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Get sessions
    sessions = db.query(models.StrengthSession).filter(
        models.StrengthSession.athlete_id == athlete_id
    ).order_by(models.StrengthSession.start_time).all()
    
    from_date = sessions[0].start_time.date()
    to_date = sessions[-1].start_time.date()
    
    print('='*60)
    print('3. REPLAY & VALIDATION ANALYSIS')
    print('='*60)
    
    # Get all rep-level data from sessions
    rep_predictions = []
    day_states = []
    
    for s in sessions:
        raw = s.raw_data or {}
        rep_log = s.rep_level_log or []
        
        # Process rep-level log if available
        for entry in rep_log:
            pred = {
                'session_id': s.id,
                'lift': s.lift.value,
                'date': s.start_time.date().isoformat(),
                'set_idx': entry.get('set_idx', 0),
                'rep_idx': entry.get('rep_idx', 0),
                'A_l': entry.get('A_l'),
                'A_sys': entry.get('A_sys'),
                'A_M': entry.get('A_M'),
            }
            rep_predictions.append(pred)
    
    print(f"Rep-level entries collected: {len(rep_predictions)}")
    
    # v9.2: Simulate day-by-day with proper carryover
    from datetime import timedelta
    from app.services.engine_orchestrator import EngineOrchestrator
    from app.domain.day_engine import decay_day_state_to_date, DayEngineParams, DailyImpulses, EnduranceImpulses, StrengthImpulses, SetImpulse
    from app.domain.rep_engine import simulate_strength_session, LiftVelocityProfile, SessionInput, SetInput, RepEngineParams
    
    orchestrator = EngineOrchestrator(db)
    day_params = DayEngineParams()
    rep_params = RepEngineParams()
    
    # Group sessions by date
    sessions_by_date = {}
    for s in sessions:
        d = s.start_time.date()
        if d not in sessions_by_date:
            sessions_by_date[d] = []
        sessions_by_date[d].append(s)
    
    # Simulate day-by-day
    day_data = []
    current_date = from_date
    previous_state = None
    
    while current_date <= to_date:
        # Step 1: Decay from previous day (if any)
        if previous_state:
            # Decay previous state to current date
            day_state = decay_day_state_to_date(previous_state, current_date, day_params)
        else:
            # First day - get initial state
            day_state = orchestrator._get_or_create_day_state(athlete_id, current_date, create=False)
            if not day_state:
                # Create fresh state
                day_state = orchestrator._get_or_create_day_state(athlete_id, current_date, create=True)
        
        # Step 2: Apply any sessions on this date
        if current_date in sessions_by_date:
            for session in sessions_by_date[current_date]:
                # Get lift profile
                profile_db = db.query(models.LiftProfile).filter(
                    models.LiftProfile.athlete_id == athlete_id,
                    models.LiftProfile.lift == session.lift
                ).first()
                
                if profile_db:
                    profile = LiftVelocityProfile(
                        lift=session.lift.value,
                        a=profile_db.a,
                        b=profile_db.b
                    )
                    
                    # Get session data
                    raw_data = session.raw_data or {}
                    sets_data = raw_data.get('sets', [])
                    
                    # Convert to rep_engine inputs
                    set_inputs = []
                    for set_data in sets_data:
                        velocities = set_data.get('velocities', [])
                        if not velocities:
                            velocities = [1.0] * set_data.get('reps', 1)
                        
                        set_inputs.append(SetInput(
                            lift=session.lift.value,
                            load_kg=set_data.get('load_kg', 0),
                            velocities=velocities,
                            rest_before_sec=set_data.get('rest_sec', 0)
                        ))
                    
                    # Run rep_engine simulation
                    init_A_local = {session.lift.value: max(0.1, 1.0 - day_state.per_lift.get(session.lift.value, PerLiftState()).D_l / 2)}
                    init_A_sys = max(0.1, 1.0 - day_state.D_sys / 2)
                    
                    session_input = SessionInput(
                        sets=set_inputs,
                        profiles={session.lift.value: profile},
                        init_A_local=init_A_local,
                        init_A_sys=init_A_sys,
                        init_M=0.0,
                        R_mito=day_state.R_mito,
                        params=rep_params
                    )
                    
                    rep_output = simulate_strength_session(session_input)
                    
                    # Compute strength impulses
                    total_tonnage = sum(s.load_kg * len(s.velocities) for s in set_inputs)
                    total_reps = sum(len(s.velocities) for s in set_inputs)
                    avg_intensity = total_tonnage / max(total_reps, 1) if total_reps > 0 else 0
                    
                    # Simplified impulse calculation
                    u_lift = total_tonnage * 0.001  # Simplified
                    u_sys = total_tonnage * 0.0005  # Simplified
                    u_legs = u_lift if session.lift.value in ['squat', 'deadlift', 'clean'] else 0
                    u_legs_high_intensity = u_legs if avg_intensity > 70 else 0
                    
                    strength_impulses = StrengthImpulses(
                        per_lift={session.lift.value: u_lift},
                        u_sys=u_sys,
                        u_legs=u_legs,
                        u_met=0.0,
                        u_legs_high_intensity=u_legs_high_intensity,
                        sets=[]
                    )
                    
                    # Update day state with session
                    daily_impulses = DailyImpulses(
                        strength=strength_impulses,
                        endurance=EnduranceImpulses(
                            u_E_Z2=0.0, u_E_HIIT=0.0, u_E_total=0.0,
                            mode='cycling', has_HIIT=False, has_Z2=False
                        ),
                        date=current_date
                    )
                    
                    from app.domain.day_engine import update_day_state
                    day_state = update_day_state(day_state, daily_impulses, day_params)
        
        # Store the day state
        day_entry = {
            'date': current_date.isoformat(),
            'D_sys': day_state.D_sys,
            'R_mito': day_state.R_mito,
            'E_fat': day_state.E_fat,
            'T_legs': day_state.T_legs
        }
        
        # Add per-lift states
        for lift, lift_state in day_state.per_lift.items():
            day_entry[f"D_l_{lift}"] = lift_state.D_l
            day_entry[f"F_l_{lift}"] = lift_state.F_l
            day_entry[f"C_l_{lift}"] = lift_state.C_l
        
        day_data.append(day_entry)
        
        # Update for next iteration
        previous_state = day_state
        current_date += timedelta(days=1)
    
    print(f"Day states collected: {len(day_data)} (simulated day-by-day with carryover)")
    
    # Save day states
    with open(artifacts_dir / 'day_states.json', 'w') as f:
        json.dump(day_data, f, indent=2)
    
    # Calculate basic metrics
    print('\n' + '='*60)
    print('4. METRICS SUMMARY')
    print('='*60)
    
    # Per-lift breakdown
    lift_metrics = defaultdict(lambda: {'sessions': 0, 'tonnage': 0, 'avg_intensity': []})
    
    for s in sessions:
        lift = s.lift.value
        lift_metrics[lift]['sessions'] += 1
        lift_metrics[lift]['tonnage'] += s.tonnage
        lift_metrics[lift]['avg_intensity'].append(s.avg_intensity)
    
    print(f"{'Lift':<15} {'Sessions':>10} {'Tonnage':>12} {'Avg Int':>10}")
    print('-'*60)
    for lift in sorted(lift_metrics.keys()):
        m = lift_metrics[lift]
        avg_int = sum(m['avg_intensity']) / len(m['avg_intensity']) if m['avg_intensity'] else 0
        print(f"{lift:<15} {m['sessions']:>10} {m['tonnage']:>12.1f} {avg_int:>10.2f}")
    
    # Save trend eval
    trend_eval = {
        'athlete_id': athlete_id,
        'date_range': [str(from_date), str(to_date)],
        'total_sessions': len(sessions),
        'day_states_tracked': len(day_data),
        'lift_metrics': dict(lift_metrics),
        'notes': [
            'No VBT data available (velocity coverage 0%)',
            'Rep-level predictions based on model internal state',
            'Day-level states tracked via EngineOrchestrator'
        ]
    }
    
    with open(artifacts_dir / 'trend_eval.json', 'w') as f:
        json.dump(trend_eval, f, indent=2, default=str)
    
    print(f'\n✓ Trend eval saved to: {artifacts_dir}/trend_eval.json')
    
    # List all artifacts
    print('\n' + '='*60)
    print('5. ARTIFACTS GENERATED')
    print('='*60)
    for f in sorted(artifacts_dir.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:<30} {size:>10} bytes")

if __name__ == '__main__':
    main()
