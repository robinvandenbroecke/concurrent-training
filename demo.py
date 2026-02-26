#!/usr/bin/env python3
"""
Demo script for Concurrent Training API
This script demonstrates all major functionality using the TestClient
so no external server is needed.
"""
import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=" * 60)
print("CONCURRENT TRAINING API - DEMO")
print("=" * 60)

# 1. Health check
print("\n1. Health Check")
print("-" * 40)
response = client.get("/health")
print(f"Status: {response.json()}")

# 2. Create athlete
print("\n2. Create Athlete")
print("-" * 40)
response = client.post("/athletes", json={"name": "Demo Athlete"})
athlete = response.json()
athlete_id = athlete["id"]
print(f"Created: {athlete['name']} (ID: {athlete_id})")

# 3. Check readiness (initial)
print("\n3. Initial Readiness Check")
print("-" * 40)
response = client.get(f"/readiness/today?athlete_id={athlete_id}")
readiness = response.json()
print(f"Overall: {readiness['overall']:.1f}%")
print(f"Endurance: {readiness['endurance']:.1f}%")
print("Per-lift:")
for lift, score in readiness['per_lift'].items():
    print(f"  {lift}: {score:.1f}%")

# 4. Log strength session
print("\n4. Log Strength Session (Squat)")
print("-" * 40)
strength_session = {
    "athlete_id": athlete_id,
    "lift": "squat",
    "start_time": "2024-01-15T10:00:00",
    "sets": [
        {
            "weight": 100.0,
            "target_reps": 5,
            "reps": [
                {"weight": 100.0, "velocity": 0.45, "rep_num": 1, "rest_before": 180},
                {"weight": 100.0, "velocity": 0.42, "rep_num": 2, "rest_before": 3},
                {"weight": 100.0, "velocity": 0.38, "rep_num": 3, "rest_before": 3},
                {"weight": 100.0, "velocity": 0.35, "rep_num": 4, "rest_before": 3},
                {"weight": 100.0, "velocity": 0.32, "rep_num": 5, "rest_before": 3},
            ]
        },
        {
            "weight": 100.0,
            "target_reps": 5,
            "reps": [
                {"weight": 100.0, "velocity": 0.40, "rep_num": 1, "rest_before": 240},
                {"weight": 100.0, "velocity": 0.36, "rep_num": 2, "rest_before": 3},
                {"weight": 100.0, "velocity": 0.33, "rep_num": 3, "rest_before": 3},
            ]
        }
    ]
}
response = client.post("/sessions/strength", json=strength_session)
session = response.json()
print(f"Logged: {session['tonnage']:.0f}kg tonnage")
print(f"Avg intensity: {session['avg_intensity']:.2f}")
print(f"Session ID: {session['id']}")

# 5. Log Z2 endurance session
print("\n5. Log Endurance Session (Z2 Cycling)")
print("-" * 40)
endurance_session = {
    "athlete_id": athlete_id,
    "sport": "cycling",
    "start_time": "2024-01-15T08:00:00",
    "duration_minutes": 45.0,
    "intensity_type": "z2"
}
response = client.post("/sessions/endurance", json=endurance_session)
session = response.json()
print(f"Duration: {session['duration_minutes']}min")
print(f"Z2 component: {session['u_E_Z2']:.1f}min (builds R_mito)")
print(f"HIIT component: {session['u_E_HIIT']:.1f}min")

# 6. Log HIIT running session
print("\n6. Log Endurance Session (HIIT Running)")
print("-" * 40)
hiit_session = {
    "athlete_id": athlete_id,
    "sport": "running",
    "start_time": "2024-01-15T14:00:00",
    "duration_minutes": 30.0,
    "intensity_type": "hiit"
}
response = client.post("/sessions/endurance", json=hiit_session)
session = response.json()
print(f"Duration: {session['duration_minutes']}min")
print(f"Z2 component: {session['u_E_Z2']:.1f}min")
print(f"HIIT component: {session['u_E_HIIT']:.1f}min (adds interference)")

# 7. Update day state (normally done by cron)
print("\n7. Update Day State")
print("-" * 40)
response = client.post(f"/admin/update-day/{athlete_id}")
state = response.json()
print(f"D_sys (system fatigue): {state['D_sys']:.3f}")
print(f"R_mito (recovery capacity): {state['R_mito']:.3f}")
print(f"E_fat (endurance fatigue): {state['E_fat']:.3f}")

# 8. Check readiness after sessions
print("\n8. Readiness After Training")
print("-" * 40)
response = client.get(f"/readiness/today?athlete_id={athlete_id}")
readiness = response.json()
print(f"Overall: {readiness['overall']:.1f}%")
print(f"Endurance: {readiness['endurance']:.1f}%")
print("Per-lift:")
for lift, score in readiness['per_lift'].items():
    print(f"  {lift}: {score:.1f}%")
print("\nExplanations:")
for exp in readiness['explanations']:
    print(f"  • {exp}")

# 9. Autoregulation suggestion
print("\n9. Autoregulation Suggestion")
print("-" * 40)
autoreg_request = {
    "athlete_id": athlete_id,
    "lift": "squat",
    "current_weight": 105.0,
    "target_v_low": 0.35,
    "target_v_high": 0.45,
    "vl_max": 20.0,
    "planned_reps": 5,
    "current_reps_done": 0
}
response = client.post("/strength/autoregulate", json=autoreg_request)
suggestion = response.json()
print(f"Predicted velocity: {suggestion['predicted_velocity']:.3f} m/s")
print(f"Current VL: {suggestion['current_vl']:.1f}%")
print(f"Continue: {suggestion['continue_set']}")
if suggestion['load_change'] != 0:
    print(f"Load change: {suggestion['load_change']*100:+.1f}%")
if suggestion['rest_suggestion']:
    print(f"Rest: {suggestion['rest_suggestion']}")
print("Messages:")
for msg in suggestion['messages']:
    print(f"  • {msg}")

print("\n" + "=" * 60)
print("DEMO COMPLETE")
print("=" * 60)
print("\nTo run the full server with web UI:")
print("  ./start.sh")
print("\nThen open: http://localhost:8000/static/index.html")
