"""Scenario, boundary, regression and property tests for the user-facing engine.

These tests prove software properties (determinism, no fabricated values, no
look-ahead, unit handling). They do not validate physiology.
"""
import json
import math
import random
from pathlib import Path

import pytest

from app.science import CONTRACT_VERSION, ENGINE_VERSION
from app.science.contract import EngineRequest
from app.science.critical_power import fit_critical_power, w_prime_balance
from app.science.load_velocity import LVPoint, fit_profile, velocity_loss
from app.science.service import evaluate, input_digest
from app.science.strength_estimates import estimate_e1rm

FIXTURES = Path(__file__).resolve().parents[1] / "webapp" / "tests" / "fixtures" / "contracts"


def strength_session(day, sets, sid=None, exercise="back_squat", start=None, power=False, meta=True):
    velocity_meta = {"metric": "mean_concentric", "deviceId": "manual-entry", "source": "manual"} if meta else None
    return {"id": sid or f"s-{day}-{exercise}", "date": day, "type": "kracht", "durationMinutes": 60, "startTime": start,
            "exercises": [{"exerciseId": exercise, "lift": "squat", "power": power, "sets": [
                {"setNum": i + 1, "weight": w, "completedReps": len(v), "velocities": v, "rpe": rpe, "kind": kind,
                 "velocityMeta": velocity_meta} for i, (w, v, rpe, kind) in enumerate(sets)]}]}


def profile_sets(shift=0.0):
    # v = 1.30 - 0.008 * load, measured on three warm-up loads and one work load.
    return [(w, [round(1.30 - 0.008 * w + shift, 3)], None, "warmup") for w in (40, 60, 80)] + \
           [(100, [round(0.50 + shift, 3), round(0.46 + shift, 3), round(0.42 + shift, 3)], 8, "work")]


# ── load-velocity ──────────────────────────────────────────────────────────

def test_profile_recovers_known_line_and_refuses_extrapolation():
    points = [LVPoint(w, 1.30 - 0.008 * w, "2026-01-01") for w in (40, 60, 80, 100)]
    profile = fit_profile(points)
    assert profile.status == "ok"
    assert profile.slope_ms_per_kg == pytest.approx(-0.008) and profile.intercept_ms == pytest.approx(1.30)
    assert profile.expected(70) == pytest.approx(0.74)
    assert profile.expected(120) is None and profile.expected(20) is None   # no 1RM or light-load extrapolation


@pytest.mark.parametrize("points,reason", [
    ([(60, .8), (80, .64)], "too_few_points"),
    ([(60, .8), (60, .81), (62.5, .78), (62.5, .79)], "too_few_distinct_loads"),
    ([(90, .5), (95, .46), (100, .42), (100, .43)], "load_range_too_narrow"),
])
def test_profile_requires_enough_spread(points, reason):
    profile = fit_profile([LVPoint(w, v, "2026-01-01") for w, v in points])
    assert profile.status == "insufficient_data" and reason in profile.reasons and profile.intercept_ms is None


def test_profile_rejects_wrong_sign_and_noise_instead_of_repairing_them():
    rising = fit_profile([LVPoint(w, 0.3 + 0.004 * w, "d") for w in (40, 60, 80, 100)])
    assert rising.status == "rejected" and rising.expected(60) is None
    noisy = fit_profile([LVPoint(w, v, "d") for w, v in ((40, .9), (60, .5), (80, .85), (100, .45))])
    assert noisy.status == "rejected" and "poor_linear_fit" in noisy.reasons


def test_velocity_loss_uses_fastest_rep_and_keeps_missing_missing():
    assert velocity_loss([0.50, 0.52, 0.39]) == pytest.approx(0.25)      # fastest rep, not the first
    assert velocity_loss([0.5, None, 0.4]) == pytest.approx(0.2)
    assert velocity_loss([0.5, 0.45, None]) is None                       # last rep unmeasured
    assert velocity_loss([None, None, 0.4]) is None and velocity_loss([0.5]) is None
    assert velocity_loss([0.40, 0.45]) == 0.0                             # never negative


# ── repetition-based estimate ──────────────────────────────────────────────

def test_e1rm_is_bounded_estimate_and_absent_without_effort_rating():
    estimate = estimate_e1rm(100, 5, 8)
    assert estimate.status == "ok" and estimate.low_kg < estimate.value_kg < estimate.high_kg
    assert estimate.value_kg == pytest.approx(100 * 36 / (37 - 7))          # Brzycki, 5 reps + 2 in reserve
    assert estimate_e1rm(100, 5, None).status == "insufficient_data"       # RPE unknown stays unknown
    assert estimate_e1rm(100, 5, 5).status == "insufficient_data"
    assert estimate_e1rm(60, 20, 9).status == "insufficient_data"
    assert estimate_e1rm(0, 8, 9).status == "not_applicable"
    assert estimate_e1rm(140, 1, 10).value_kg == 140


# ── critical power ─────────────────────────────────────────────────────────

def test_critical_power_recovers_parameters_from_exact_efforts():
    cp, wp = 280.0, 20000.0
    fit = fit_critical_power([(t, cp + wp / t) for t in (180, 420, 900)])
    assert fit.status == "ok" and fit.cp_w == pytest.approx(cp) and fit.w_prime_j == pytest.approx(wp)
    assert "only_three_efforts_one_degree_of_freedom" in fit.warnings


def test_critical_power_refuses_thin_or_inconsistent_input():
    assert fit_critical_power([(300, 320), (720, 290)]).status == "insufficient_data"
    assert fit_critical_power([(20, 900), (60, 600), (3600, 250)]).status == "insufficient_data"   # outside 2-20 min
    inconsistent = fit_critical_power([(180, 300), (420, 340), (900, 280)])
    assert inconsistent.status == "rejected" and "power_not_decreasing_with_duration" in inconsistent.reasons


def test_w_prime_balance_properties():
    cp, wp = 250.0, 20000.0
    assert w_prime_balance([cp] * 600, cp, wp)[-1] == pytest.approx(wp)
    assert w_prime_balance([cp + 100] * 100, cp, wp)[-1] == pytest.approx(wp - 10000)
    # Exhaustion time at constant severe power equals W'/(P-CP).
    trace = w_prime_balance([cp + 200] * 100, cp, wp)
    assert trace[-1] == pytest.approx(0.0, abs=1e-6)
    # Recovery is monotone, bounded by W', and independent of the time step.
    depleted = [cp + 150] * 60
    fine = w_prime_balance(depleted + [100.0] * 300, cp, wp, 1.0)
    coarse = w_prime_balance([cp + 150] * 12 + [100.0] * 60, cp, wp, 5.0)
    assert fine[-1] == pytest.approx(coarse[-1])
    recovery = fine[60:]
    assert all(b >= a for a, b in zip(recovery, recovery[1:])) and recovery[-1] < wp
    # A dropout is not zero watts.
    gap = w_prime_balance([cp + 100, None, cp + 100], cp, wp)
    assert gap[1] is None and gap[2] == pytest.approx(wp - 200)
    with pytest.raises(ValueError):
        w_prime_balance([float("nan")], cp, wp)


def test_w_prime_fixture_shared_with_the_typescript_implementation():
    fixture = json.loads((FIXTURES / "wbal_v1.json").read_text())
    trace = w_prime_balance(fixture["power_w"], fixture["cp_w"], fixture["w_prime_j"], fixture["dt_s"])
    expected = fixture["expected_balance_j"]
    assert len(trace) == len(expected) and [v is None for v in trace] == [v is None for v in expected]
    assert [v for v in trace if v is not None] == pytest.approx([v for v in expected if v is not None], rel=1e-9)


# ── service ────────────────────────────────────────────────────────────────

def build(sessions, as_of="2026-03-31", **extra):
    return EngineRequest.model_validate({"asOfDate": as_of, "sessions": sessions, **extra})


def test_empty_account_makes_no_statement():
    out = evaluate(build([]))
    assert out["engine_version"] == ENGINE_VERSION and out["contract_version"] == CONTRACT_VERSION
    assert out["strength"] == [] and out["concurrent"] == [] and out["load"]["daily"] == []
    assert out["endurance"]["reference"]["source"] == "none" and out["endurance"]["cp_model"]["status"] == "insufficient_data"
    assert "no_validated_readiness_score" in out["limitations"]


def test_sessions_without_velocity_or_rpe_yield_history_but_no_estimates():
    out = evaluate(build([strength_session("2026-03-30", [(100, [None, None, None], None, "work")])]))
    block = out["strength"][0]
    assert block["history"] == [{"date": "2026-03-30", "top_work_weight_kg": 100, "reps": 3}]
    assert block["e1rm_estimate"]["status"] == "insufficient_data" and block["velocity"] == []
    assert block["last_session_velocity_loss"][0]["velocity_loss"] is None


def test_latest_session_is_compared_with_a_profile_from_earlier_sessions_only():
    earlier = [strength_session(f"2026-03-{d:02d}", profile_sets()) for d in (10, 17)]
    slow = strength_session("2026-03-24", profile_sets(shift=-0.08))
    group = evaluate(build(earlier + [slow]))["strength"][0]["velocity"][0]
    deviation = group["latest_deviation"]
    assert deviation["status"] == "ok" and deviation["interpretation"] == "slower" and deviation["deviation_pct"] < -8
    # The slow day must not have been used to calibrate its own reference.
    assert deviation["calibration_points"] == 8
    # Changing a FUTURE session cannot change an earlier evaluation (no look-ahead).
    before = evaluate(build(earlier + [slow], as_of="2026-03-20"))
    after = evaluate(build(earlier + [strength_session("2026-03-24", profile_sets(shift=+0.2))], as_of="2026-03-20"))
    assert before["strength"] == after["strength"] and before["sessions_after_as_of_ignored"] == 1


def test_velocity_metrics_and_devices_are_never_pooled():
    a = strength_session("2026-03-10", profile_sets(), sid="a")
    b = strength_session("2026-03-17", profile_sets(), sid="b", meta=False)
    groups = evaluate(build([a, b]))["strength"][0]["velocity"]
    assert [(g["metric"], g["sessions_with_velocity"]) for g in groups] == [("mean_concentric", 1), ("unspecified", 1)]
    assert "velocity_metric_unknown" in groups[1]["warnings"]


def test_bodyweight_and_other_exercises_do_not_borrow_each_others_numbers():
    squat = strength_session("2026-03-10", profile_sets())
    pull = strength_session("2026-03-10", [(0, [None] * 6, 9, "work")], sid="p", exercise="pull_up")
    pull["exercises"][0]["loadType"] = "bodyweight"
    out = {b["exercise"]: b for b in evaluate(build([squat, pull]))["strength"]}
    assert out["pull_up"]["e1rm_estimate"]["status"] == "not_applicable" and out["pull_up"]["velocity"] == []
    assert out["back_squat"]["e1rm_estimate"]["basis"]["weight_kg"] == 100


def test_forecast_check_needs_eight_out_of_sample_sessions_and_reports_baselines():
    rng = random.Random(7)
    sessions = [strength_session(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", profile_sets(shift=rng.gauss(0, 0.01))) for i in range(0, 84, 7)]
    few = evaluate(build(sessions[:6]))["strength"][0]["velocity"][0]["forecast_check"]
    assert few["status"] == "insufficient_data"
    full = evaluate(build(sessions))["strength"][0]["velocity"][0]["forecast_check"]
    assert full["status"] == "ok" and full["test_sessions"] == 10
    assert {"fixed_profile", "last_observation", "mean_of_last_3", "M0", "M1"} == {m["model"] for m in full["models"]}
    # Pure noise around a fixed profile: the dynamic model must not be declared better.
    assert full["dynamic_model_beats_simple_baselines"] is False


def endurance(day, minutes=60, sid=None, **result):
    return {"id": sid or f"e-{day}", "date": day, "type": "duur", "durationMinutes": minutes,
            "startTime": result.pop("startTime", None),
            "enduranceResult": {"sport": "cycling", "durationMinutes": minutes, "intensityType": "easy", **result}}


def test_endurance_load_units_methods_and_missing_data():
    stream = {"sampleSeconds": 1, "watts": [200.0] * 1800 + [None] * 600 + [0.0] * 1200}
    sessions = [endurance("2026-03-28", power=stream), endurance("2026-03-29", averagePowerW=200),
                endurance("2026-03-30", rpe=6), endurance("2026-03-31")]
    out = evaluate(build(sessions, endurance={"thresholdPowerW": 250}))
    rows = {r["date"]: r["endurance"][0] for r in out["load"]["daily"]}
    assert rows["2026-03-28"]["method"] == "relative_power_squared_time_integral"
    assert rows["2026-03-28"]["load"] == pytest.approx(0.64 * 30, abs=0.05) and rows["2026-03-28"]["missing_samples"] == 600
    assert rows["2026-03-29"]["load"] == pytest.approx(0.64 * 60, abs=0.05)
    assert rows["2026-03-30"] == {"minutes": 60, "load": 360.0, "method": "session_rpe_times_minutes"}
    assert rows["2026-03-31"]["load"] is None and rows["2026-03-31"]["method"] == "duration_only"
    week = out["load"]["last_7_days"]
    assert week["endurance_minutes"] == 240 and week["endurance_load"] is None and week["endurance_load_method"] == "mixed_methods"
    assert out["endurance"]["reference"]["source"] == "user_entered_threshold_not_cp"
    # Without any reference power the stream is NOT converted into a load.
    none = evaluate(build(sessions[:1]))["load"]["daily"][0]["endurance"][0]
    assert none["load"] is None and none["method"] == "duration_only"


def test_cp_fit_is_preferred_over_entered_values_only_when_it_passes():
    efforts = [{"durationSeconds": t, "powerW": 280 + 20000 / t} for t in (180, 420, 900, 1200)]
    good = evaluate(build([], endurance={"maximalEfforts": efforts, "thresholdPowerW": 250}))["endurance"]
    assert good["reference"] == {"source": "cp_fit_from_maximal_efforts", "power_w": 280.0, "w_prime_j": 20000.0, "sport": "cycling"}
    bad = evaluate(build([], endurance={"maximalEfforts": efforts[:2], "criticalPowerW": 270, "wPrimeJ": 18000}))["endurance"]
    assert bad["cp_model"]["status"] == "insufficient_data" and bad["reference"]["source"] == "user_entered_cp"


def test_concurrent_flags_depend_on_measured_gap_and_stay_unknown_without_times():
    power = strength_session("2026-03-30", profile_sets(), power=True, start="2026-03-30T17:00:00+02:00")
    ride = endurance("2026-03-30", startTime="2026-03-30T15:30:00+02:00")
    flag = evaluate(build([power, ride]))["concurrent"][0]
    assert flag["code"] == "explosive_work_within_3h_of_endurance" and flag["gap_hours"] == 1.5 and flag["evidence"] == "schumann_2022"
    apart = evaluate(build([power, endurance("2026-03-30", startTime="2026-03-30T07:00:00+02:00")]))["concurrent"][0]
    assert apart["code"] == "same_day_separated_by_3h_or_more"
    unknown = evaluate(build([strength_session("2026-03-30", profile_sets()), endurance("2026-03-30")]))["concurrent"][0]
    assert unknown["code"] == "same_day_order_and_gap_unknown" and unknown["gap_hours"] is None


def test_engine_is_deterministic_order_independent_and_json_safe():
    rng = random.Random(11)
    sessions = [strength_session(f"2026-03-{d:02d}", profile_sets(shift=rng.uniform(-.05, .05)), sid=f"s{d}") for d in range(1, 29, 3)]
    sessions += [endurance(f"2026-03-{d:02d}", rpe=5, sid=f"e{d}") for d in range(2, 29, 4)]
    first = evaluate(build(sessions))
    shuffled = sessions[:]
    rng.shuffle(shuffled)
    second = evaluate(build(shuffled))
    for key in ("strength", "endurance", "load", "concurrent"):
        assert first[key] == second[key]
    assert first["input_digest"] != second["input_digest"]          # the digest identifies the exact input
    assert input_digest(build(sessions)) == first["input_digest"]

    def finite(node):
        if isinstance(node, float):
            assert math.isfinite(node)
        elif isinstance(node, dict):
            [finite(v) for v in node.values()]
        elif isinstance(node, list):
            [finite(v) for v in node]
    finite(first)
    json.dumps(first, allow_nan=False)


def test_random_valid_inputs_never_crash_or_emit_non_finite_numbers():
    rng = random.Random(2026)
    for _ in range(150):
        sessions = []
        for i in range(rng.randint(0, 12)):
            day = f"2026-03-{rng.randint(1, 28):02d}"
            if rng.random() < .6:
                sets = [(rng.choice([0, 20, 60, 100, 180]), [rng.choice([None, round(rng.uniform(.05, 2.5), 2)]) for _ in range(rng.randint(1, 8))],
                         rng.choice([None, 4, 7, 8.5, 10]), rng.choice(["work", "warmup"])) for _ in range(rng.randint(1, 5))]
                sessions.append(strength_session(day, sets, sid=f"k{i}", exercise=rng.choice(["back_squat", "bench_press"]), meta=rng.random() < .7))
            else:
                sessions.append(endurance(day, minutes=rng.choice([0, 20, 90]), sid=f"d{i}", rpe=rng.choice([None, 3, 9]),
                                          averagePowerW=rng.choice([None, 0, 180])))
        out = evaluate(build(sessions, endurance=rng.choice([{}, {"thresholdPowerW": 240}])))
        json.dumps(out, allow_nan=False)


def test_contract_fixture_matches_the_frozen_expected_response():
    request = json.loads((FIXTURES / "engine_v1_request.json").read_text())
    expected = json.loads((FIXTURES / "engine_v1_response.json").read_text())
    assert evaluate(EngineRequest.model_validate(request)) == expected


def test_contract_rejects_impossible_measurements_instead_of_clipping_them():
    bad = strength_session("2026-03-30", [(100, [9.9], 8, "work")])
    with pytest.raises(ValueError):
        build([bad])
    with pytest.raises(ValueError):
        build([endurance("2026-03-30", averagePowerW=-5)])
    with pytest.raises(ValueError):
        build([], as_of="30-03-2026")


def test_engine_does_not_depend_on_the_legacy_compartment_model():
    import subprocess
    import sys
    code = ("import sys; import app.science.service; "
            "bad=[m for m in sys.modules if m.startswith(('app.domain.rep_engine','app.domain.day_engine','app.domain.legacy_model','app.services'))]; "
            "print(bad); sys.exit(1 if bad else 0)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


# ── corrections of the November 2026 audit (see AUDIT_REPORT.md) ───────────

def test_e1rm_is_continuous_and_monotone_in_reps_and_effort():
    """SCI-04: no jump between a true single and a single with half a rep in reserve."""
    singles = [estimate_e1rm(100, 1, rpe).value_kg for rpe in (10, 9.5, 9, 8.5, 8)]
    assert singles[0] == 100
    steps = [b / a - 1 for a, b in zip(singles, singles[1:])]
    assert all(0 < step < 0.02 for step in steps)
    by_reps = [estimate_e1rm(100, reps, 9).value_kg for reps in range(1, 12)]
    assert all(b > a for a, b in zip(by_reps, by_reps[1:]))


def test_noise_limit_follows_student_t_for_small_profiles():
    """SCI-02: with four calibration points a z of 2.5 is ordinary noise (t = 4.30, 2 df)."""
    from app.science.load_velocity import t_critical_95
    assert t_critical_95(2) == pytest.approx(4.303) and t_critical_95(10) == pytest.approx(2.228)
    assert t_critical_95(0) == float("inf") and t_critical_95(500) == pytest.approx(1.96)
    assert all(t_critical_95(df) >= t_critical_95(df + 1) for df in range(1, 200))
    rng = random.Random(7)
    def session(day, shift):
        return strength_session(day, [(w, [round(1.30 - 0.008 * w + shift + rng.gauss(0, 0.004), 3)], None, "warmup")
                                      for w in (40, 60, 80, 100)])
    out = evaluate(build([session("2026-03-01", 0.0), session("2026-03-08", -0.006)], as_of="2026-03-08"))
    deviation = out["strength"][0]["velocity"][0]["latest_deviation"]
    assert deviation["status"] == "ok" and deviation["noise_limit"] == pytest.approx(4.3, abs=0.01)
    assert abs(deviation["z"]) > 2 and deviation["interpretation"] == "within_noise"


def test_false_alarm_rate_of_the_deviation_flag_is_near_five_percent():
    """SCI-02 as a property: identical athlete, noise only. The old |z| < 2 rule flagged far more."""
    rng, flagged, old_rule, runs = random.Random(11), 0, 0, 400
    for _ in range(runs):
        def session(day):
            return strength_session(day, [(w, [round(1.30 - 0.008 * w + rng.gauss(0, 0.02), 4)], None, "warmup")
                                          for w in (40, 60, 80, 100)])
        out = evaluate(build([session("2026-03-01"), session("2026-03-08")], as_of="2026-03-08"))
        deviation = out["strength"][0]["velocity"][0]["latest_deviation"]
        if deviation["status"] != "ok":
            continue
        flagged += deviation["interpretation"] != "within_noise"
        old_rule += abs(deviation["z"]) >= 2
    assert flagged / runs < 0.08 < old_rule / runs


def test_power_reference_is_not_carried_over_to_another_sport():
    """SCI-01: cycling CP/FTP must not scale running power."""
    run = endurance("2026-03-30", sport="running", averagePowerW=300, rpe=5)
    ride = endurance("2026-03-31", averagePowerW=200)
    out = evaluate(build([run, ride], endurance={"thresholdPowerW": 250}))
    rows = {r["date"]: r["endurance"][0] for r in out["load"]["daily"]}
    assert rows["2026-03-30"]["method"] == "session_rpe_times_minutes"
    assert rows["2026-03-30"]["power_not_used"] == "no_power_reference_for_this_sport"
    assert rows["2026-03-31"]["method"] == "average_power_squared_duration" and "power_not_used" not in rows["2026-03-31"]
    assert out["endurance"]["reference"]["sport"] == "cycling"
    running = evaluate(build([run], endurance={"sport": "running", "thresholdPowerW": 300}))
    assert running["load"]["daily"][0]["endurance"][0]["load"] == pytest.approx(60.0)


def test_critical_power_uses_best_effort_per_duration_and_warns_about_short_or_old_sets():
    """SCI-03."""
    cp, wp = 280.0, 20000.0
    exact = [(t, cp + wp / t) for t in (180, 420, 900)]
    with_repeat = fit_critical_power(exact + [(420, 300.0)])              # a clearly sub-maximal second 7-min effort
    assert with_repeat.status == "ok" and with_repeat.cp_w == pytest.approx(cp)
    assert "repeated_durations_best_effort_used" in with_repeat.warnings
    short = fit_critical_power([(t, cp + wp / t) for t in (150, 300, 480)])
    assert "no_effort_of_10_min_or_longer_cp_may_be_overestimated" in short.warnings
    assert "no_effort_of_10_min_or_longer_cp_may_be_overestimated" not in fit_critical_power(exact).warnings
    assert "effort_dates_unknown" in fit_critical_power(exact).warnings
    assert "efforts_span_more_than_6_weeks" in fit_critical_power(exact, span_days=90).warnings
    assert not {"effort_dates_unknown", "efforts_span_more_than_6_weeks"} & set(fit_critical_power(exact, span_days=10).warnings)
    dated = [{"durationSeconds": t, "powerW": cp + wp / t, "date": d}
             for t, d in ((180, "2026-01-05"), (420, "2026-03-20"), (900, "2026-03-27"))]
    assert "efforts_span_more_than_6_weeks" in evaluate(build([], endurance={"maximalEfforts": dated}))["endurance"]["cp_model"]["warnings"]
    assert fit_critical_power([(300, 320), (300, 330), (300.2, 310)]).status == "insufficient_data"   # one duration, three tries


def test_impossible_dates_and_conflicting_duplicates_are_refused_not_crashed_on():
    """DATA-01/02: the stored pattern accepts 2026-02-30; the engine must answer with a validation error."""
    good = strength_session("2026-03-30", profile_sets())
    for bad in ({"asOfDate": "2026-02-30", "sessions": []}, {"asOfDate": "2026-03-31", "sessions": [{**good, "date": "2026-13-01"}]},
                {"asOfDate": "2026-03-31", "sessions": [], "endurance": {"maximalEfforts": [{"durationSeconds": 300, "powerW": 300, "date": "2026-00-10"}]}}):
        with pytest.raises(ValueError):
            EngineRequest.model_validate(bad)
    once = evaluate(build([good]))
    twice = evaluate(build([good, dict(good)]))
    assert twice["duplicate_sessions_ignored"] == 1 and twice["sessions_used"] == 1
    assert twice["load"] == once["load"] and twice["strength"] == once["strength"]
    changed = {**good, "durationMinutes": 61}
    with pytest.raises(ValueError):
        build([good, changed])


def test_concurrent_flag_reports_order_and_ignores_upper_body_only_explosive_work():
    """SCI-05."""
    ride = endurance("2026-03-30", startTime="2026-03-30T15:30:00+02:00")
    lower = strength_session("2026-03-30", profile_sets(), power=True, start="2026-03-30T17:00:00+02:00")
    flag = evaluate(build([lower, ride]))["concurrent"][0]
    assert flag["order"] == "endurance_first" and flag["lower_body_strength_work"] is None    # region not recorded
    lower["exercises"][0]["region"] = "lower"
    early = {**lower, "startTime": "2026-03-30T14:00:00+02:00"}
    flag = evaluate(build([early, ride]))["concurrent"][0]
    assert flag["order"] == "strength_first" and flag["lower_body_strength_work"] is True
    assert flag["code"] == "explosive_work_within_3h_of_endurance"
    upper = strength_session("2026-03-30", profile_sets(), power=True, start="2026-03-30T17:00:00+02:00")
    upper["exercises"][0]["region"] = "upper"
    flag = evaluate(build([upper, ride]))["concurrent"][0]
    assert flag["code"] == "strength_within_3h_of_endurance" and flag["evidence"] == "context_only"
    assert flag["lower_body_strength_work"] is False and flag["explosive_work"] is False
