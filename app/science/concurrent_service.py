"""Builds the concurrent model's inputs from stored sessions and reports its output.

Doses and observations are derived, never stored back: measurements stay as
they were recorded. Every assumption made for lack of data is counted in
``data`` so that the client can show it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
from typing import Dict, List, Optional, Tuple

from app.science import concurrent as cm
from app.science.contract import EngineRequest, PlanRequest, SessionIn
from app.science.load_velocity import fit_profile, t_critical_95
from app.science.strength_estimates import estimate_e1rm

EPOCH = datetime(2000, 1, 1)
LOWER_LIFTS = {"squat", "deadlift", "clean", "power_clean"}
UPPER_LIFTS = {"bench", "press"}
DECLARED_INTENSITY = {"easy": 0.60, "z2": 0.65, "long": 0.65, "tempo": 0.85, "threshold": 1.00, "hiit": 1.10}
E1RM_NOISE_RATIO = 1.25
PRIORITY_WEIGHTS = {"kracht": {"strength": 1.0, "endurance": 0.5}, "duur": {"strength": 0.5, "endurance": 1.0},
                    "balans": {"strength": 1.0, "endurance": 1.0}}


def _days(moment: datetime) -> float:
    return (moment - EPOCH).total_seconds() / 86400.0


def _local_days(day: date, hour: float, zone: str = "UTC") -> float:
    wall = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
    aware = wall.replace(tzinfo=ZoneInfo(zone))
    utc = aware.astimezone(timezone.utc)
    if utc.astimezone(ZoneInfo(zone)).replace(tzinfo=None) != wall:
        raise ValueError("planned local time does not exist because of daylight saving")
    return _days(utc.replace(tzinfo=None))


def _moment(days: float, zone: str = "UTC") -> str:
    return (EPOCH + timedelta(days=days)).replace(tzinfo=timezone.utc, microsecond=0).astimezone(ZoneInfo(zone)).isoformat(timespec="minutes")


def _wall(session: SessionIn, zone: str = "UTC") -> Tuple[float, bool]:
    """Wall-clock time of a session; noon of its date when no start time was stored."""
    if session.startTime:
        try:
            parsed = datetime.fromisoformat(session.startTime.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return _days(parsed.astimezone(timezone.utc).replace(tzinfo=None)), True
        except ValueError:
            pass
    return _local_days(date.fromisoformat(session.date), 12, zone), False


def _region(ex) -> str:
    if ex.region != "unknown":
        return ex.region
    return "lower" if ex.lift in LOWER_LIFTS else "upper" if ex.lift in UPPER_LIFTS else "unknown"


def _endurance_dose(session: SessionIn, reference_w: Optional[float], reference_sport: Optional[str]) -> Tuple[float, str]:
    """Threshold-relative minutes / 60. The source says how much of it is measured."""
    from app.science.service import _endurance_session_load
    e = session.enduranceResult
    entry = _endurance_session_load(session, reference_w, reference_sport)
    if entry["load"] is not None and entry["method"] != "session_rpe_times_minutes":
        return entry["load"] / cm.MINUTES_PER_DOSE_UNIT, "measured_power"
    if e.rpe is not None:
        # Assumption: session RPE 7 corresponds to the reference intensity.
        return e.durationMinutes * min(1.3, max(0.4, e.rpe / 7.0)) ** 2 / cm.MINUTES_PER_DOSE_UNIT, "session_rpe_assumed_scale"
    relative = DECLARED_INTENSITY.get(e.intensityType)
    if relative is not None:
        return e.durationMinutes * relative ** 2 / cm.MINUTES_PER_DOSE_UNIT, "declared_intensity_assumed_scale"
    return e.durationMinutes * 0.7 ** 2 / cm.MINUTES_PER_DOSE_UNIT, "duration_only_assumed_moderate"


def build_events(sessions: List[SessionIn], reference_w: Optional[float], reference_sport: Optional[str], zone: str = "UTC") -> Tuple[list, dict]:
    events, sources = [], Counter()
    info = {"sessions_without_start_time": 0, "strength_sets_region_unknown": 0, "same_day_pairs_with_unknown_gap": 0,
            "endurance_other_sport": 0}
    timed: Dict[str, list] = defaultdict(list)
    for session in sessions:
        t, known = _wall(session, zone)
        info["sessions_without_start_time"] += not known
        timed[session.date].append((session.type, known))
        if session.type == "kracht":
            lower = upper = 0.0
            for ex in session.exercises:
                region = _region(ex)
                for s in ex.sets:
                    if s.kind != "work" or s.completedReps <= 0:
                        continue
                    weight = 0.5 if (s.rpe is not None and s.rpe < 6) else 1.0
                    if region == "lower":
                        lower += weight
                    elif region == "upper":
                        upper += weight
                    elif region == "full":
                        lower, upper = lower + weight, upper + 0.5 * weight
                    else:
                        # Unknown stays unknown: split evenly and count it.
                        lower, upper = lower + 0.5 * weight, upper + 0.5 * weight
                        info["strength_sets_region_unknown"] += 1
            if lower or upper:
                events.append((cm.Event(t, lower / cm.SETS_PER_DOSE_UNIT, upper / cm.SETS_PER_DOSE_UNIT), known))
        elif session.enduranceResult and session.enduranceResult.durationMinutes > 0:
            dose, source = _endurance_dose(session, reference_w, reference_sport)
            sources[source] += 1
            sport = session.enduranceResult.sport
            if sport in {"running", "cycling"}:
                events.append((cm.Event(t, endurance_lower=dose), known))
            elif sport == "swimming":
                events.append((cm.Event(t, endurance_upper=dose), known))
            else:
                info["endurance_other_sport"] += 1
                events.append((cm.Event(t, endurance_other=dose), known))
    for day in timed.values():
        strength = [known for kind, known in day if kind == "kracht"]
        endurance = [known for kind, known in day if kind == "duur"]
        info["same_day_pairs_with_unknown_gap"] += sum(1 for a in strength for b in endurance if not (a and b))
    # Proximity is a measured gap; sessions without a start time never count as "within 3 h".
    marked = cm.mark_proximity([e for e, known in events if known])
    unmarked = [e for e, known in events if not known]
    info["endurance_dose_sources"] = dict(sorted(sources.items()))
    info["sessions"] = len(events)
    return sorted(marked + unmarked, key=lambda e: e.t), info


def build_observations(request: EngineRequest, sessions: List[SessionIn], endurance: dict) -> Tuple[list, list, dict]:
    from app.science.service import CALIBRATION_SEARCH_SESSIONS, _exercise_key, _lv_points
    info = {"strength_series": [], "endurance_reference": None, "exercises_region_unknown": 0}
    by_exercise: Dict[str, list] = defaultdict(list)
    for session in sessions:
        if session.type == "kracht":
            for ex in session.exercises:
                if any(s.completedReps > 0 for s in ex.sets):
                    by_exercise[_exercise_key(ex)].append((session, ex))
    strength: List[cm.Observation] = []
    for key in sorted(by_exercise):
        records = sorted(by_exercise[key], key=lambda item: (_wall(item[0], request.timeZone)[0], item[0].id))
        region = _region(records[-1][1])
        if region == "unknown":
            info["exercises_region_unknown"] += 1
            continue
        region = "upper" if region == "upper" else "lower"
        candidates: Dict[str, list] = {}
        groups = sorted({((s.velocityMeta.metric if s.velocityMeta else "unspecified"),
                          (s.velocityMeta.deviceId if s.velocityMeta else "unspecified"))
                         for _, ex in records for s in ex.sets if any(v is not None for v in s.velocities)})
        for metric, device in groups:
            per_session = [(session, _lv_points(session, ex, metric, device)) for session, ex in records]
            per_session = [item for item in per_session if item[1]]
            calibration, split = None, None
            for index in range(2, min(len(per_session), CALIBRATION_SEARCH_SESSIONS + 1)):
                candidate = fit_profile([p for _, pts in per_session[:index] for p in pts])
                if candidate.status == "ok":
                    calibration, split = candidate, index
                    break
            if calibration is None:
                continue
            series = f"{key}|velocity|{metric}|{device}"
            rows = []
            for session, points in per_session[split:]:
                usable = [p for p in points if calibration.in_range(p.load_kg)]
                if usable:
                    value = sum(math.log(p.velocity_ms / calibration.expected(p.load_kg)) for p in usable) / len(usable)
                    rows.append(cm.Observation(_wall(session, request.timeZone)[0], series, "strength", region, value))
            candidates[series] = rows
        if records[-1][1].loadType == "weight":
            rows = []
            for session, ex in records:
                estimates = [estimate_e1rm(s.weight, s.completedReps, s.rpe) for s in ex.sets if s.kind == "work"]
                values = [e.value_kg for e in estimates if e.status == "ok"]
                if values:
                    rows.append(cm.Observation(_wall(session, request.timeZone)[0], f"{key}|e1rm_estimate", "strength", region,
                                               math.log(max(values)), E1RM_NOISE_RATIO))
            candidates[f"{key}|e1rm_estimate"] = rows
        if candidates:
            # One observation type per exercise, so one session is not counted as two measurements.
            series, rows = max(sorted(candidates.items()), key=lambda item: (len(item[1]), "|velocity|" in item[0]))
            if rows:
                strength += rows
                info["strength_series"].append({"series": series, "observations": len(rows), "region": region})
    profile = request.endurance
    efforts: List[cm.Observation] = []
    cp, wp = None, None
    if profile.criticalPowerW and profile.wPrimeJ:
        cp, wp, info["endurance_reference"] = profile.criticalPowerW, profile.wPrimeJ, "user_entered_cp_and_w_prime"
    elif endurance["cp_model"]["status"] == "ok":
        cp, wp = endurance["cp_model"]["cp_w"], endurance["cp_model"]["w_prime_j"]
        info["endurance_reference"] = "cp_fit_on_the_same_efforts_circular"
    # A reference fitted to these same outcomes is not independent validation data.
    if cp and info["endurance_reference"] != "cp_fit_on_the_same_efforts_circular":
        region = "upper" if profile.sport == "swimming" else "lower"
        for e in profile.maximalEfforts:
            if e.date and e.date <= request.asOfDate and 120 <= e.durationSeconds <= 1200:
                t = _local_days(date.fromisoformat(e.date), 12, request.timeZone)
                efforts.append(cm.Observation(t, f"{profile.sport}|maximal_effort_power", "endurance", region,
                                              math.log(e.powerW / (cp + wp / e.durationSeconds))))
    return strength, efforts, info


def _round(value, digits=3):
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _coefficients(fit_: cm.Fit, domain: str) -> dict:
    out = {}
    limit = t_critical_95(fit_.df)
    for term in cm.TERMS[domain]:
        mean, scale = fit_.coefficient(term)
        prior_mean, prior_sd = cm.PRIORS[domain][term]
        out[term] = {"mean": _round(mean, 5), "low": _round(mean - limit * scale, 5), "high": _round(mean + limit * scale, 5),
                     "prior_mean": prior_mean, "prior_sd": prior_sd, "informed_by_data": _round(fit_.informed_by_data(term), 2),
                     "unit": "log_performance_per_dose_unit"}
    return out


def _domain_report(domain: str, result: dict) -> dict:
    fit_ = result["fit"]
    report = {"status": result["status"], "observations": result["observations"], "coefficients": _coefficients(fit_, domain),
              "basis": "group_level_priors_only" if result["status"] == "prior_only" else "priors_updated_with_own_data"}
    if result["status"] == "prior_only":
        report["reason"] = result["reason"]
        return report
    forward = result["walk_forward"]
    report.update({
        "noise_sd_log": _round(math.sqrt(fit_.sigma2), 4),
        "log_evidence": {k: _round(v, 2) for k, v in result["log_evidence"].items()},
        "walk_forward": {"tests": forward["tests"], "mae_log": {k: _round(v, 4) for k, v in forward["mae"].items()},
                         "interval_coverage_95": _round(forward["interval_coverage_95"], 2)},
        "own_dynamics_supported": result["own_dynamics_supported"], "interaction_supported": result["interaction_supported"],
        "beats_last_observation": result["beats_last_observation"], "verdict": result["verdict"]})
    return report


def _prepare(request: EngineRequest, sessions: List[SessionIn], endurance: dict):
    # A CP fitted to the complete effort history is retrospective. Do not let
    # those future outcomes rescale doses in the chronological prediction test.
    profile = request.endurance
    reference = {"power_w": profile.criticalPowerW or profile.thresholdPowerW,
                 "sport": profile.sport if profile.criticalPowerW or profile.thresholdPowerW else None}
    events, dose_info = build_events(sessions, reference["power_w"], reference["sport"], request.timeZone)
    strength, efforts, observation_info = build_observations(request, sessions, endurance)
    # Freeze hyperparameters before the prediction test. Selecting them from the
    # complete history would leak held-out outcomes into the walk-forward test.
    constants = cm.TimeConstants()
    constants_info = {"source": "defaults", "reason": "fixed_before_walk_forward_validation"}
    results = {"strength": cm.calibrate("strength", strength, events, constants),
               "endurance": cm.calibrate("endurance", efforts, events, constants)}
    return events, constants, constants_info, results, {**dose_info, **observation_info}


def _state_rows(fits: Dict[str, cm.Fit], events, constants, start: float, days: int = 4, zone: str = "UTC") -> list:
    times = [start + d for d in range(days)]
    states = cm.states_at(events, times, constants)
    rows = []
    for t, state in zip(times, states):
        row = {"at": _moment(t, zone)}
        for name, domain, region in (("strength_lower", "strength", "lower"), ("strength_upper", "strength", "upper"),
                                     ("endurance", "endurance", "lower")):
            fit_ = fits[domain]
            x = cm.features(domain, region, state)
            own, _ = fit_.effect(x, ("fatigue",))
            cross, _ = fit_.effect(x, ("cross_fatigue",))
            total, scale = cm.readiness(fit_, domain, region, state)
            limit = t_critical_95(fit_.df) * scale
            row[name] = {"own_fatigue_pct": _round(cm.percent(own), 1), "cross_fatigue_pct": _round(cm.percent(cross), 1),
                         "total_pct": _round(cm.percent(total), 1), "low_pct": _round(cm.percent(total - limit), 1),
                         "high_pct": _round(cm.percent(total + limit), 1)}
        rows.append(row)
    return rows


LIMITATIONS = ["not_validated_on_real_athletes", "prior_magnitudes_are_order_of_magnitude_not_population_estimates",
               "percentages_are_model_based_expected_performance_differences_not_measurements",
               "no_injury_or_health_statement",
               "observational_fit_does_not_establish_causal_interference",
               "walk_forward_is_exploratory_not_external_validation"]


def concurrent_block(request: EngineRequest, sessions: List[SessionIn], as_of: date, endurance: dict) -> dict:
    events, constants, constants_info, results, data = _prepare(request, sessions, endurance)
    fits = {domain: results[domain]["fit"] for domain in results}
    start = _local_days(as_of + timedelta(days=1), 0, request.timeZone)     # end of the as-of day
    return {
        "model_version": cm.MODEL_VERSION,
        "time_constants_days": {"fatigue_strength": constants.fatigue_strength, "fatigue_endurance": constants.fatigue_endurance,
                                "fitness_strength": constants.fitness_strength, "fitness_endurance": constants.fitness_endurance,
                                **{k: (_round(v, 2) if isinstance(v, float) else v) for k, v in constants_info.items()}},
        "data": data,
        "strength": _domain_report("strength", results["strength"]),
        "endurance": _domain_report("endurance", results["endurance"]),
        "expected_fatigue_effect": _state_rows(fits, events, constants, start, zone=request.timeZone),
        "limitations": LIMITATIONS,
    }


def plan_week(request: PlanRequest) -> dict:
    """Rank arrangements of the given sessions over the free slots."""
    from app.science.service import _endurance, input_digest
    as_of = date.fromisoformat(request.asOfDate)
    unique = list({s.id: s for s in request.sessions}.values())
    sessions = [s for s in unique if date.fromisoformat(s.date) <= as_of]
    endurance = _endurance(request)
    events, constants, constants_info, results, data = _prepare(request, sessions, endurance)
    fits = {domain: results[domain]["fit"] for domain in results}
    dates = sorted(date.fromisoformat(d) for d in request.availableDates)
    if dates[0] <= as_of:
        raise ValueError("available dates must lie after asOfDate")
    planned = []
    for item in request.planSessions:
        if item.kind.startswith("strength"):
            if item.workSets <= 0:
                raise ValueError(f"{item.label}: a strength session needs workSets")
            planned.append(cm.PlannedSession(item.label, "strength", item.kind.split("_")[1], item.workSets / cm.SETS_PER_DOSE_UNIT, item.key))
        else:
            if item.minutes <= 0:
                raise ValueError(f"{item.label}: an endurance session needs minutes")
            dose = item.minutes * item.relativeIntensity ** 2 / cm.MINUTES_PER_DOSE_UNIT
            planned.append(cm.PlannedSession(item.label, "endurance", "upper" if item.kind == "endurance_swim" else "lower", dose, item.key))
    slots = [_local_days(d, h, request.timeZone) for d in dates for h in sorted(request.slotHours)]
    if len(planned) > len(slots):
        raise ValueError("more sessions than free slots")
    start = _local_days(dates[0], 0, request.timeZone)
    state = cm.states_at(events, [start], constants)[0]
    horizon_end = _local_days(dates[-1] + timedelta(days=1), 0, request.timeZone)
    weights = PRIORITY_WEIGHTS[request.priority]
    result = cm.suggest_week(fits, state, start, planned, slots, constants, horizon_end, weights)

    def tidy(option: dict) -> dict:
        return {"score": _round(option["score"], 5),
                "sessions": [{"label": s["label"], "start": _moment(s["t"], request.timeZone), "domain": s["domain"], "key": s["key"],
                              "expected_fatigue_effect_pct": _round(s["readiness_pct"], 1),
                              "low_pct": _round(s["readiness_low_pct"], 1), "high_pct": _round(s["readiness_high_pct"], 1),
                              "within_3h_of_endurance": s["within_3h_of_endurance"]} for s in option["sessions"]],
                "end_of_horizon": {k: {m: _round(v, 2) for m, v in values.items()} for k, values in option["end_of_horizon"].items()}}
    best = [tidy(option) for option in result["best"]]
    return {"model_version": cm.MODEL_VERSION, "as_of_date": request.asOfDate, "input_digest": input_digest(request),
            "priority": request.priority, "method": result["method"], "arrangements_evaluated": result["arrangements_evaluated"],
            "basis": {domain: ("group_level_priors_only" if results[domain]["status"] == "prior_only" else "priors_updated_with_own_data")
                      for domain in results},
            # Only an exhaustive search knows the worst arrangement.
            "difference_best_to_worst_pct": (_round(100 * math.expm1(result["spread_log_score"]), 2)
                                             if result["method"] == "exhaustive" else None),
            "options": best, "data": data, "limitations": LIMITATIONS + ["ranking_reflects_model_assumptions_not_proven_outcomes"]}
