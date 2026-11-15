"""Concurrent model: mathematical properties, parameter recovery on SIMULATED athletes, planning.

Simulated data prove that the estimator and the comparison logic behave as
specified. They say nothing about whether real athletes follow this model.
"""
import math
import random

import numpy as np
import pytest

from app.science import concurrent as cm
from app.science.concurrent_service import build_events, plan_week
from app.science.contract import EngineRequest, PlanRequest
from app.science.service import evaluate

TC = cm.TimeConstants()


def simulate(seed, days=240, cross=0.05, fatigue=0.05, fitness=0.004, interference=0.0, noise=0.015):
    """Lower-body strength observations under varied strength and endurance training."""
    rng = random.Random(seed)
    events = []
    for day in range(days):
        block = (day // 28) % 3                      # varied load so that fitness is not constant
        if day % 7 in (0, 2, 4) or (block == 2 and day % 7 == 5):
            events.append(cm.Event(day + 0.75, strength_lower=rng.uniform(0.6, 1.6) * (0.6 if block == 0 else 1.0)))
        roll = rng.random()
        if roll < 0.25:
            events.append(cm.Event(day + 0.35, endurance_lower=rng.uniform(0.4, 1.4)))      # morning, before strength
        elif roll < 0.40:
            events.append(cm.Event(day + 0.70, endurance_lower=rng.uniform(0.4, 1.4)))      # just before strength
        elif roll < 0.55:
            events.append(cm.Event(day + 0.85, endurance_lower=rng.uniform(0.4, 1.4)))      # after strength
    events = cm.mark_proximity(events)
    times = [e.t for e in events if e.strength_lower > 0]
    states = cm.states_at(events, times, TC)
    truth = np.array([fitness, fatigue, cross, interference])
    observations = [cm.Observation(t, "squat", "strength", "lower",
                                   0.1 + float(cm.features("strength", "lower", s) @ truth) + rng.gauss(0, noise))
                    for t, s in zip(times, states)]
    return events, observations


# ── mathematical properties ────────────────────────────────────────────────

def test_traces_are_exact_in_time_and_independent_of_event_order_and_query_splitting():
    events = [cm.Event(0.0, strength_lower=1.0), cm.Event(1.3, endurance_lower=0.8), cm.Event(2.9, strength_upper=0.5)]
    direct = cm.states_at(events, [10.0], TC)[0]
    stepped = cm.states_at(events, [0.5, 1.3, 2.0, 2.9, 7.7, 10.0], TC)[-1]
    shuffled = cm.states_at(list(reversed(events)) + [cm.Event(5.0)], [10.0], TC)[0]
    assert direct == pytest.approx(stepped, rel=1e-12) and direct == pytest.approx(shuffled, rel=1e-12)
    assert direct[cm.FS_L] == pytest.approx(math.exp(-10.0 / TC.fatigue_strength))
    assert direct[cm.GS_L] == pytest.approx(math.exp(-10.0 / TC.fitness_strength))
    # A session at exactly the query time is not yet part of the state (no look-ahead within a session).
    assert cm.states_at(events, [0.0], TC)[0] == pytest.approx(np.zeros(9))


def test_fatigue_is_temporary_and_never_subtracts_from_the_level():
    """Answer to LEG-03: after rest the fatigue part returns to zero; only the slow trace remains."""
    prior = cm.prior_fit("strength")
    hard = [cm.Event(float(d), strength_lower=2.0, endurance_lower=1.5) for d in range(5)]
    fresh, rested = cm.states_at(hard, [5.0, 65.0], TC)
    assert cm.readiness(prior, "strength", "lower", fresh)[0] < -0.05
    assert abs(cm.readiness(prior, "strength", "lower", rested)[0]) < 1e-9
    after_rest = cm.readiness(prior, "strength", "lower", cm.states_at(hard, [8.0, 12.0, 20.0], TC)[0])[0]
    assert cm.readiness(prior, "strength", "lower", fresh)[0] < after_rest < 0


def test_dose_is_relative_so_a_stronger_athlete_gets_the_same_dose_for_the_same_session():
    """Answer to LEG-04."""
    def session(scale):
        return {"id": "s", "date": "2026-03-02", "type": "kracht", "startTime": "2026-03-02T18:00:00",
                "exercises": [{"exerciseId": "back_squat", "lift": "squat", "sets": [
                    {"setNum": i + 1, "weight": 80 * scale, "completedReps": 5, "rpe": 8} for i in range(3)]}]}
    doses = []
    for scale in (1, 2):
        request = EngineRequest.model_validate({"asOfDate": "2026-03-02", "sessions": [session(scale)]})
        events, _ = build_events(request.sessions, None, None)
        doses.append(events[0].strength_lower)
    assert doses[0] == doses[1] == pytest.approx(0.3)


def test_missing_start_times_are_never_turned_into_a_same_session_flag():
    strength = {"id": "s", "date": "2026-03-02", "type": "kracht", "exercises": [{"lift": "squat", "sets": [
        {"setNum": 1, "weight": 100, "completedReps": 5}]}]}
    ride = {"id": "e", "date": "2026-03-02", "type": "duur", "enduranceResult": {"sport": "cycling", "durationMinutes": 60, "intensityType": "tempo"}}
    request = EngineRequest.model_validate({"asOfDate": "2026-03-02", "sessions": [strength, ride]})
    events, info = build_events(request.sessions, None, None)
    assert info["sessions_without_start_time"] == 2 and info["same_day_pairs_with_unknown_gap"] == 1
    assert all(e.near_endurance == 0 for e in events)
    assert info["endurance_dose_sources"] == {"declared_intensity_assumed_scale": 1}
    timed = [dict(strength, startTime="2026-03-02T18:00:00Z"), dict(ride, startTime="2026-03-02T16:30:00Z")]
    events, info = build_events(EngineRequest.model_validate({"asOfDate": "2026-03-02", "sessions": timed}).sessions, None, None)
    assert [e.near_endurance for e in events if e.strength_lower] == [1.0] and info["same_day_pairs_with_unknown_gap"] == 0


# ── estimation ─────────────────────────────────────────────────────────────

def test_without_data_the_model_is_exactly_its_priors():
    result = cm.calibrate("strength", [], [], TC)
    assert result["status"] == "prior_only"
    for term in cm.TERMS["strength"]:
        mean, scale = result["fit"].coefficient(term)
        assert mean == pytest.approx(cm.PRIORS["strength"][term][0]) and scale == pytest.approx(cm.PRIORS["strength"][term][1])
        assert result["fit"].informed_by_data(term) == 0.0


def test_coefficients_are_recovered_from_a_long_simulated_series_with_honest_intervals():
    inside = {term: 0 for term in ("fatigue", "cross_fatigue")}
    for seed in range(12):
        events, observations = simulate(seed, cross=0.05, fatigue=0.05)
        result = cm.calibrate("strength", observations, events, TC)
        fit_ = result["fit"]
        limit = cm.t_critical_95(fit_.df)
        for term, truth in (("fatigue", 0.05), ("cross_fatigue", 0.05)):
            mean, scale = fit_.coefficient(term)
            inside[term] += abs(mean - truth) <= limit * scale
            assert abs(mean - truth) < 0.02 and fit_.informed_by_data(term) > 0.8
    assert all(count >= 10 for count in inside.values())          # 95 % intervals cover in at least 10 of 12 runs


def test_fitness_is_reported_as_poorly_determined_when_training_barely_varies():
    """Constant training makes the slow trace collinear with the level: the model must say so."""
    events = [cm.Event(d + 0.75, strength_lower=1.0) for d in range(0, 400, 2)]
    rng = random.Random(3)
    times = [e.t for e in events if e.t > 250]
    states = cm.states_at(events, times, TC)
    observations = [cm.Observation(t, "squat", "strength", "lower", rng.gauss(0, 0.02))
                    for t, s in zip(times, states)]
    fit_ = cm.calibrate("strength", observations, events, TC)["fit"]
    assert fit_.informed_by_data("fitness") < 0.3


def test_interaction_is_only_claimed_when_it_is_in_the_data():
    present = sum(cm.calibrate("strength", obs, ev, TC)["interaction_supported"]
                  for ev, obs in (simulate(seed, cross=0.05) for seed in range(10)))
    absent = sum(cm.calibrate("strength", obs, ev, TC)["interaction_supported"]
                 for ev, obs in (simulate(100 + seed, cross=0.0) for seed in range(10)))
    assert present >= 9 and absent <= 1


def test_out_of_sample_error_and_interval_coverage_on_simulated_data():
    events, observations = simulate(42, cross=0.05)
    result = cm.calibrate("strength", observations, events, TC)
    forward = result["walk_forward"]
    assert forward["tests"] > 60
    assert forward["mae"]["cross"] < forward["mae"]["own"] < forward["mae"]["level"]
    assert forward["mae"]["cross"] < forward["mae"]["last_observation"] and result["beats_last_observation"]
    assert 0.88 <= forward["interval_coverage_95"] <= 1.0


def test_pure_noise_does_not_produce_dynamics_or_a_win_over_the_naive_baseline():
    rng = random.Random(5)
    events, observations = simulate(5)
    noise_only = [cm.Observation(o.t, o.series, o.domain, o.region, rng.gauss(0, 0.02)) for o in observations]
    result = cm.calibrate("strength", noise_only, events, TC)
    assert not result["own_dynamics_supported"] and not result["interaction_supported"]
    assert result["verdict"] == "not_shown_in_own_data"


def test_time_constants_stay_at_their_defaults_unless_the_data_clearly_prefer_others():
    events, observations = simulate(1, days=60)
    chosen, info = cm.select_time_constants(observations[:8], [], events)
    assert chosen == TC and info["source"] == "defaults"
    slow = cm.TimeConstants(fatigue_strength=3.0, fatigue_endurance=2.0)
    rng = random.Random(9)
    events, _ = simulate(9, days=300)
    times = [e.t for e in events if e.strength_lower > 0]
    truth = np.array([0.004, 0.06, 0.06, 0.0])
    observations = [cm.Observation(t, "squat", "strength", "lower", float(cm.features("strength", "lower", s) @ truth) + rng.gauss(0, 0.008))
                    for t, s in zip(times, cm.states_at(events, times, slow))]
    chosen, info = cm.select_time_constants(observations, [], events)
    assert info["source"] == "selected_by_evidence" and chosen.fatigue_strength == 3.0 and chosen.fatigue_endurance == 2.0


# ── planning ───────────────────────────────────────────────────────────────

def _plan_inputs():
    fits = {"strength": cm.prior_fit("strength"), "endurance": cm.prior_fit("endurance")}
    sessions = [cm.PlannedSession("zware benen", "strength", "lower", 1.2, key=True),
                cm.PlannedSession("intervallen", "endurance", "lower", 1.0, key=True),
                cm.PlannedSession("rustige duur", "endurance", "lower", 0.5),
                cm.PlannedSession("bovenlichaam", "strength", "upper", 1.0)]
    slots = [d + h for d in range(4) for h in (8 / 24, 18 / 24)]
    return fits, sessions, slots


def test_planner_keeps_key_sessions_fresh_and_agrees_with_exhaustive_search():
    fits, sessions, slots = _plan_inputs()
    weights = {"strength": 1.0, "endurance": 1.0}
    exact = cm.suggest_week(fits, np.zeros(9), 0.0, sessions, slots, TC, 4.0, weights)
    assert exact["method"] == "exhaustive" and exact["arrangements_evaluated"] == math.perm(8, 4)
    best = exact["best"][0]
    by_label = {s["label"]: s for s in best["sessions"]}
    # Neither key session is placed in the wake of the other lower-body key session.
    assert by_label["zware benen"]["readiness_pct"] > -1.0 and by_label["intervallen"]["readiness_pct"] > -1.5
    assert not any(s["within_3h_of_endurance"] for s in best["sessions"])
    assert exact["spread_log_score"] > 0
    heuristic = cm.suggest_week(fits, np.zeros(9), 0.0, sessions, slots, TC, 4.0, weights, exact_limit=400)
    assert heuristic["method"] == "heuristic"
    assert heuristic["best"][0]["score"] <= best["score"] + 1e-12
    assert heuristic["best"][0]["score"] >= best["score"] - 0.25 * exact["spread_log_score"]


def test_a_combined_session_is_scored_worse_than_the_same_work_hours_apart():
    fits, _, _ = _plan_inputs()
    weights = {"strength": 1.0, "endurance": 1.0}
    lift = cm.PlannedSession("explosief", "strength", "lower", 1.0, key=True)
    ride = cm.PlannedSession("duur", "endurance", "lower", 1.0)
    together = cm.evaluate_schedule(fits, np.zeros(9), 0.0, [(0.70, ride), (0.75, lift)], TC, 7.0, weights)
    apart = cm.evaluate_schedule(fits, np.zeros(9), 0.0, [(0.33, ride), (0.75, lift)], TC, 7.0, weights)
    reverse = cm.evaluate_schedule(fits, np.zeros(9), 0.0, [(0.33, lift), (0.75, ride)], TC, 7.0, weights)
    assert together["sessions"][1]["within_3h_of_endurance"] and not apart["sessions"][1]["within_3h_of_endurance"]
    assert together["sessions"][1]["readiness_pct"] < apart["sessions"][1]["readiness_pct"] < 0
    assert together["end_of_horizon"]["strength_lower"]["adaptation_change_pct"] < apart["end_of_horizon"]["strength_lower"]["adaptation_change_pct"]
    assert together["score"] < apart["score"]
    assert reverse["sessions"][0]["readiness_pct"] == pytest.approx(0.0)       # strength first: fresh for the lift


# ── service ────────────────────────────────────────────────────────────────

def test_engine_reports_the_model_as_priors_only_for_a_new_account_and_plans_with_them():
    out = evaluate(EngineRequest.model_validate({"asOfDate": "2026-03-01", "sessions": []}))["concurrent_model"]
    assert out["strength"]["status"] == out["endurance"]["status"] == "prior_only"
    assert out["strength"]["basis"] == "group_level_priors_only"
    assert out["expected_fatigue_effect"][0]["strength_lower"]["total_pct"] == 0.0
    assert "not_validated_on_real_athletes" in out["limitations"]
    request = {"asOfDate": "2026-03-01", "sessions": [], "priority": "kracht",
               "availableDates": ["2026-03-02", "2026-03-03", "2026-03-05"],
               "planSessions": [{"label": "benen", "kind": "strength_lower", "workSets": 12, "key": True},
                                {"label": "tempo", "kind": "endurance", "minutes": 60, "relativeIntensity": 0.85},
                                {"label": "boven", "kind": "strength_upper", "workSets": 10}]}
    plan = plan_week(PlanRequest.model_validate(request))
    assert plan == plan_week(PlanRequest.model_validate(request))                # deterministic
    assert plan["method"] == "exhaustive" and len(plan["options"]) == 3
    assert plan["basis"] == {"strength": "group_level_priors_only", "endurance": "group_level_priors_only"}
    legs = next(s for s in plan["options"][0]["sessions"] if s["label"] == "benen")
    assert legs["expected_fatigue_effect_pct"] > -0.5 and not legs["within_3h_of_endurance"]
    with pytest.raises(ValueError):
        plan_week(PlanRequest.model_validate({**request, "availableDates": ["2026-03-01"]}))
    with pytest.raises(ValueError):
        PlanRequest.model_validate({**request, "availableDates": ["2026-02-30"]})


def test_engine_calibrates_on_stored_sessions_and_shows_fatigue_after_recent_training():
    rng = random.Random(2)
    sessions = []
    for week in range(10):
        for offset, rpe in ((0, 8), (3, 8.5)):
            day = 2 + week * 7 + offset
            date_text = f"2026-{1 + (day - 1) // 28:02d}-{1 + (day - 1) % 28:02d}"
            load = 100 + week + rng.choice([0, 2.5])
            sessions.append({"id": f"k{week}{offset}", "date": date_text, "type": "kracht", "startTime": f"{date_text}T18:00:00",
                             "exercises": [{"exerciseId": "back_squat", "lift": "squat", "sets": [
                                 {"setNum": i + 1, "weight": load, "completedReps": 5, "rpe": rpe} for i in range(4)]}]})
    last = max(s["date"] for s in sessions)
    out = evaluate(EngineRequest.model_validate({"asOfDate": last, "sessions": sessions}))["concurrent_model"]
    strength = out["strength"]
    assert strength["status"] == "ok" and strength["observations"] == 20
    assert out["data"]["strength_series"] == [{"series": "back_squat|e1rm_estimate", "observations": 20, "region": "lower"}]
    assert set(strength["log_evidence"]) == {"level", "own", "cross"} and strength["walk_forward"]["tests"] >= 8
    today, later = out["expected_fatigue_effect"][0]["strength_lower"], out["expected_fatigue_effect"][3]["strength_lower"]
    assert today["low_pct"] <= today["total_pct"] <= today["high_pct"]
    assert today["total_pct"] < later["total_pct"] <= 0.0 or today["total_pct"] == later["total_pct"] == 0.0
    assert out["endurance"]["status"] == "prior_only"


def test_endurance_side_recovers_cross_fatigue_from_strength_on_simulated_efforts():
    """Mirror of the strength test: lower-body strength work before a maximal effort lowers its power."""
    covered = supported = 0
    for seed in range(10):
        rng = random.Random(500 + seed)
        events, times = [], []
        for day in range(300):
            if day % 7 in (1, 4):
                events.append(cm.Event(day + 0.75, strength_lower=rng.uniform(0.6, 1.6)))
            if day % 7 in (0, 2, 5):
                events.append(cm.Event(day + 0.40, endurance_lower=rng.uniform(0.4, 1.4)))
            if day % 3 == 2:
                times.append(day + 0.35)
        truth = np.array([0.004, 0.03, 0.04, 0.0005])
        states = cm.states_at(events, times, TC)
        observations = [cm.Observation(t, "cycling|maximal_effort_power", "endurance", "lower",
                                       float(cm.features("endurance", "lower", s) @ truth) + rng.gauss(0, 0.015))
                        for t, s in zip(times, states)]
        result = cm.calibrate("endurance", observations, events, TC)
        mean, sd = result["fit"].coefficient("cross_fatigue")
        covered += abs(mean - 0.04) <= cm.t_critical_95(result["fit"].df) * sd
        supported += result["interaction_supported"]
    assert covered >= 8 and supported >= 8


def test_a_long_history_without_a_valid_velocity_profile_stays_fast():
    """The calibration search used to refit on every prefix of the history (quadratic)."""
    import time
    sessions = []
    for i in range(600):
        day = f"{2024 + i // 336}-{1 + (i % 336) // 28:02d}-{1 + i % 28:02d}"
        sessions.append({"id": f"k{i}", "date": day, "type": "kracht", "exercises": [{"exerciseId": "back_squat", "lift": "squat", "sets": [
            {"setNum": j + 1, "weight": 100 + (i * 7 + j * 3) % 20, "completedReps": 5, "rpe": 8, "velocities": [0.5, None, 0.4]} for j in range(4)]}]})
    request = EngineRequest.model_validate({"asOfDate": "2025-12-28", "sessions": sessions})
    started = time.perf_counter()
    out = evaluate(request)
    assert time.perf_counter() - started < 10.0
    assert out["concurrent_model"]["strength"]["status"] == "ok"
