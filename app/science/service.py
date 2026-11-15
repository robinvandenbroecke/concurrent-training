"""Deterministic evaluation of one athlete's own records.

Input: the athlete's stored sessions (never modified). Output: a versioned,
reproducible summary in which every statement carries a status:

``ok``                 enough of the athlete's own data and the fit passed its checks
``insufficient_data``  not enough or not the right data; no number is given
``rejected``           data were present but the model did not describe them
``not_applicable``     the statement does not apply to this record

No statement is filled in with a population default. See MODEL_REGISTER.md.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from typing import Dict, List, Optional

from app.science import CONTRACT_VERSION, ENGINE_VERSION
from app.science.contract import EngineRequest, SessionIn
from app.science.critical_power import fit_critical_power
from app.science.load_velocity import LVPoint, fit_profile, velocity_loss
from app.science.reference_model import ForecastModel
from app.science.strength_estimates import METHOD as E1RM_METHOD, estimate_e1rm

PROFILE_WINDOW_DAYS = 56
E1RM_WINDOW_DAYS = 42
LOAD_WINDOW_DAYS = 35
MIN_FORECAST_TESTS = 8
CALIBRATION_SEARCH_SESSIONS = 12   # a frozen profile must come from the first sessions with velocity
SAME_SESSION_HOURS = 3.0      # Schumann et al. 2022: same session vs >= 3 h apart


def _d(text: str) -> date:
    return date.fromisoformat(text)


def _r(value: Optional[float], digits: int = 3) -> Optional[float]:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _instant(session: SessionIn) -> Optional[datetime]:
    if not session.startTime:
        return None
    try:
        parsed = datetime.fromisoformat(session.startTime.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def input_digest(request: EngineRequest) -> str:
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── strength ────────────────────────────────────────────────────────────────

def _exercise_key(ex) -> str:
    return ex.exerciseId or ex.lift


def _lv_points(session: SessionIn, ex, metric: str, device: str) -> List[LVPoint]:
    """Fastest measured rep of the FIRST set at each load: limits within-session fatigue."""
    seen, points = set(), []
    for s in sorted(ex.sets, key=lambda item: item.setNum):
        meta = s.velocityMeta
        if ((meta.metric if meta else "unspecified"), (meta.deviceId if meta else "unspecified")) != (metric, device):
            continue
        load = round(s.weight * 2) / 2
        measured = [v for v in s.velocities[: s.completedReps or None] if v is not None]
        if load <= 0 or load in seen or not measured:
            continue
        seen.add(load)
        points.append(LVPoint(load, max(measured), session.date))
    return points


def _strength(sessions: List[SessionIn], as_of: date) -> List[dict]:
    by_exercise: Dict[str, list] = defaultdict(list)
    for session in sessions:
        if session.type != "kracht":
            continue
        for ex in session.exercises:
            if any(s.completedReps > 0 for s in ex.sets):
                by_exercise[_exercise_key(ex)].append((session, ex))
    result = []
    for key in sorted(by_exercise):
        records = sorted(by_exercise[key], key=lambda item: (item[0].date, item[0].id))
        last_session, last_ex = records[-1]
        external = last_ex.loadType == "weight"
        history = []
        for session, ex in records:
            work = [s for s in ex.sets if s.kind == "work" and s.completedReps > 0]
            if work:
                top = max(work, key=lambda s: s.weight)
                history.append({"date": session.date, "top_work_weight_kg": top.weight, "reps": top.completedReps})
        # Repetition-based estimate from the most recent qualifying session only.
        e1rm = {"status": "insufficient_data", "reason": "no_recent_set_with_rpe_7_or_higher"}
        if not external:
            e1rm = {"status": "not_applicable", "reason": "no_external_load"}
        else:
            for session, ex in reversed(records):
                if (as_of - _d(session.date)).days > E1RM_WINDOW_DAYS:
                    break
                options = [(estimate_e1rm(s.weight, s.completedReps, s.rpe), s) for s in ex.sets if s.kind == "work"]
                options = [(e, s) for e, s in options if e.status == "ok"]
                if options:
                    est, basis = max(options, key=lambda item: item[0].value_kg)
                    e1rm = {"status": "ok", "method": E1RM_METHOD, "value_kg": _r(est.value_kg, 1),
                            "low_kg": _r(est.low_kg, 1), "high_kg": _r(est.high_kg, 1),
                            "basis": {"date": session.date, "weight_kg": basis.weight, "reps": basis.completedReps, "rpe": basis.rpe}}
                    break
        groups = sorted({((s.velocityMeta.metric if s.velocityMeta else "unspecified"),
                          (s.velocityMeta.deviceId if s.velocityMeta else "unspecified"))
                         for _, ex in records for s in ex.sets if any(v is not None for v in s.velocities)})
        velocity = [_velocity_group(records, metric, device, as_of) for metric, device in groups] if external else []
        result.append({
            "exercise": key, "sessions": len(records), "last_date": last_session.date,
            "history": history[-60:], "e1rm_estimate": e1rm, "velocity": velocity,
            "last_session_velocity_loss": [
                {"set": s.setNum, "velocity_loss": _r(velocity_loss(s.velocities)),
                 "measured_reps": sum(v is not None for v in s.velocities), "reps": s.completedReps}
                for s in sorted(last_ex.sets, key=lambda item: item.setNum) if s.kind == "work" and s.completedReps > 0],
        })
    return result


def _velocity_group(records, metric: str, device: str, as_of: date) -> dict:
    per_session = [(session, ex, _lv_points(session, ex, metric, device)) for session, ex in records]
    per_session = [item for item in per_session if item[2]]
    out = {"metric": metric, "device": device, "sessions_with_velocity": len(per_session),
           "warnings": (["velocity_metric_unknown"] if metric == "unspecified" else [])
                       + (["device_unknown"] if device == "unspecified" else [])}
    window_start = as_of - timedelta(days=PROFILE_WINDOW_DAYS)
    current = fit_profile([p for s, _, pts in per_session if window_start <= _d(s.date) <= as_of for p in pts])
    out["profile"] = _profile_json(current)
    # Latest session against a profile calibrated ONLY on earlier sessions.
    out["latest_deviation"] = {"status": "insufficient_data", "reason": "no_earlier_valid_profile"}
    if len(per_session) >= 2:
        latest_session, _, latest_points = per_session[-1]
        latest = _d(latest_session.date)
        prior = fit_profile([p for s, _, pts in per_session[:-1]
                             if latest - timedelta(days=PROFILE_WINDOW_DAYS) <= _d(s.date) < latest for p in pts])
        usable = [p for p in latest_points if prior.in_range(p.load_kg)]
        if prior.status == "ok" and usable:
            rel = [(p.velocity_ms - prior.expected(p.load_kg)) / prior.expected(p.load_kg) for p in usable]
            z = [(p.velocity_ms - prior.expected(p.load_kg)) / prior.prediction_sd(p.load_kg) for p in usable]
            mean_z = sum(z) / len(z)
            # Student-t limit for the profile's residual degrees of freedom. The
            # mean over several loads of one session is treated like a single
            # observation (the loads share that day's state), which is conservative.
            limit = prior.noise_limit()
            out["latest_deviation"] = {
                "status": "ok", "date": latest_session.date, "points": len(usable),
                "deviation_pct": _r(100 * sum(rel) / len(rel), 1), "z": _r(mean_z, 2), "noise_limit": _r(limit, 2),
                "interpretation": "within_noise" if abs(mean_z) < limit else ("slower" if mean_z < 0 else "faster"),
                "calibration_points": prior.n_points}
        elif prior.status == "ok":
            out["latest_deviation"] = {"status": "insufficient_data", "reason": "latest_loads_outside_calibrated_range"}
    out["forecast_check"] = _forecast_check(per_session)
    return out


def _profile_json(profile) -> dict:
    data = {"status": profile.status, "reasons": list(profile.reasons), "points": profile.n_points,
            "distinct_loads": profile.distinct_loads}
    if profile.intercept_ms is not None:
        data.update({"load_range_kg": [profile.load_min_kg, profile.load_max_kg],
                     "intercept_ms": _r(profile.intercept_ms, 4), "slope_ms_per_kg": _r(profile.slope_ms_per_kg, 5),
                     "r2": _r(profile.r2, 3), "residual_sd_ms": _r(profile.residual_sd_ms, 4)})
    return data


def _forecast_check(per_session) -> dict:
    """Walk-forward comparison on the athlete's own series.

    Calibration (frozen): the shortest initial run of sessions that yields a
    valid profile. Every later session is predicted BEFORE it is used. Models
    use fixed, unfitted candidate parameters, so this is an honesty check of
    whether history helps at all, not a tuned forecast.
    """
    calibration, split = None, None
    # Bounded search: without the bound a history that never yields a valid profile costs O(n^2) fits.
    for index in range(1, min(len(per_session), CALIBRATION_SEARCH_SESSIONS + 1)):
        candidate = fit_profile([p for _, _, pts in per_session[:index] for p in pts])
        if candidate.status == "ok" and index >= 2:
            calibration, split = candidate, index
            break
    if calibration is None:
        return {"status": "insufficient_data", "reason": "no_frozen_calibration"}
    capacity = calibration.load_max_kg
    models = {name: ForecastModel(name) for name in ("M0", "M1")}
    errors = defaultdict(list)
    history: List[float] = []
    for session, ex, points in per_session[split:]:
        usable = [p for p in points if calibration.in_range(p.load_kg)]
        when = datetime.combine(_d(session.date), datetime.min.time()) + timedelta(hours=12)
        for model in models.values():
            model.advance(when)
        if usable:
            observed = sum(math.log(p.velocity_ms / calibration.expected(p.load_kg)) for p in usable) / len(usable)
            predictions = {"fixed_profile": 0.0, "last_observation": history[-1] if history else 0.0,
                           "mean_of_last_3": sum(history[-3:]) / len(history[-3:]) if history else 0.0}
            predictions.update({name: math.log(model.predict(1.0)) for name, model in models.items()})
            for name, value in predictions.items():
                errors[name].append(abs(observed - value))
            for model in models.values():
                model.observe(math.exp(observed), 1.0)
            history.append(observed)
        dose = sum(s.completedReps * (s.weight / capacity) ** 2 for s in ex.sets)
        for model in models.values():
            model.add_dose(strength=dose)
    tests = len(history)
    table = [{"model": name, "mae_log": _r(sum(v) / len(v), 4)} for name, v in sorted(errors.items())] if tests else []
    if tests < MIN_FORECAST_TESTS:
        return {"status": "insufficient_data", "reason": "fewer_than_8_test_sessions", "test_sessions": tests, "models": table}
    best = min(table, key=lambda row: row["mae_log"])
    baseline = min(row["mae_log"] for row in table if row["model"] in {"fixed_profile", "last_observation", "mean_of_last_3"})
    return {"status": "ok", "test_sessions": tests, "models": table, "best": best["model"],
            "dynamic_model_beats_simple_baselines": best["model"] in {"M0", "M1"} and best["mae_log"] < 0.9 * baseline,
            "note": "unfitted_candidate_parameters_no_endurance_term"}


# ── endurance ───────────────────────────────────────────────────────────────

def _endurance(request: EngineRequest) -> dict:
    profile = request.endurance
    efforts = [e for e in profile.maximalEfforts if not e.date or e.date <= request.asOfDate]
    dates = [e.date for e in efforts]
    span = (max(map(_d, dates)) - min(map(_d, dates))).days if dates and all(dates) else None
    fit = fit_critical_power([(e.durationSeconds, e.powerW) for e in efforts], span_days=span)
    model = {"status": fit.status, "reasons": list(fit.reasons), "warnings": list(fit.warnings), "efforts_used": fit.n_efforts}
    if fit.cp_w is not None:
        model.update({"cp_w": _r(fit.cp_w, 1), "w_prime_j": _r(fit.w_prime_j, 0), "se_cp_w": _r(fit.se_cp_w, 1),
                      "se_w_prime_j": _r(fit.se_w_prime_j, 0), "r2": _r(fit.r2, 4)})
    if fit.status == "ok":
        reference = {"source": "cp_fit_from_maximal_efforts", "power_w": _r(fit.cp_w, 1), "w_prime_j": _r(fit.w_prime_j, 0)}
    elif profile.criticalPowerW:
        reference = {"source": "user_entered_cp", "power_w": profile.criticalPowerW, "w_prime_j": profile.wPrimeJ}
    elif profile.thresholdPowerW:
        reference = {"source": "user_entered_threshold_not_cp", "power_w": profile.thresholdPowerW, "w_prime_j": None}
    else:
        reference = {"source": "none", "power_w": None, "w_prime_j": None}
    # A power reference belongs to one sport and one way of measuring power.
    # Cycling CP says nothing about running power from a foot pod, and vice versa.
    reference["sport"] = profile.sport if reference["power_w"] else None
    return {"cp_model": model, "reference": reference}


def _endurance_session_load(session: SessionIn, reference_w: Optional[float], reference_sport: Optional[str]) -> dict:
    e = session.enduranceResult
    base = {"minutes": e.durationMinutes, "load": None, "method": "duration_only"}
    has_power = bool(e.powerSummary or e.averagePowerW is not None or (e.power and any(v is not None for v in e.power.watts)))
    if has_power and not (reference_w and e.sport == reference_sport):
        base["power_not_used"] = "no_power_reference_for_this_sport"
    if e.sport in {"cycling", "running"} and reference_w and e.sport == reference_sport:
        try:
            if e.power and any(v is not None for v in e.power.watts):
                # Dropouts are excluded from the integral and reported; they are not zero watts.
                known = [v for v in e.power.watts if v is not None]
                value = sum((p / reference_w) ** 2 for p in known) * e.power.sampleSeconds / 60
                return {**base, "load": _r(value, 1), "method": "relative_power_squared_time_integral",
                        "missing_samples": len(e.power.watts) - len(known)}
            if e.powerSummary and e.powerSummary.recordedSeconds > 0:
                return {**base, "load": _r(e.powerSummary.sumSquaresW2s / reference_w ** 2 / 60, 1),
                        "method": "relative_power_squared_time_integral", "missing_samples": int(e.powerSummary.missingSeconds)}
            if e.averagePowerW is not None and e.durationMinutes > 0:
                total = e.durationMinutes * (e.averagePowerW / reference_w) ** 2
                return {**base, "load": _r(total, 1), "method": "average_power_squared_duration"}
        except ValueError:
            return {**base, "method": "invalid_power_input"}
    if e.rpe is not None and e.durationMinutes > 0:
        return {**base, "load": _r(e.rpe * e.durationMinutes, 1), "method": "session_rpe_times_minutes"}
    return base


# ── load context and concurrent sequencing ─────────────────────────────────

def _load(sessions: List[SessionIn], as_of: date, reference_w: Optional[float], reference_sport: Optional[str]) -> dict:
    start = as_of - timedelta(days=LOAD_WINDOW_DAYS - 1)
    days: Dict[str, dict] = {}
    for session in sessions:
        day = _d(session.date)
        if not start <= day <= as_of:
            continue
        row = days.setdefault(session.date, {"date": session.date, "strength_work_sets": 0, "strength_reps": 0,
                                             "strength_tonnage_kg": 0.0, "strength_sets_rpe_unknown": 0,
                                             "endurance_minutes": 0.0, "endurance": []})
        if session.type == "kracht":
            for ex in session.exercises:
                for s in ex.sets:
                    if s.kind == "work" and s.completedReps > 0:
                        row["strength_work_sets"] += 1
                        row["strength_reps"] += s.completedReps
                        if ex.loadType == "weight":
                            row["strength_tonnage_kg"] += s.weight * s.completedReps
                        row["strength_sets_rpe_unknown"] += s.rpe is None
        elif session.enduranceResult:
            entry = _endurance_session_load(session, reference_w, reference_sport)
            row["endurance_minutes"] += entry["minutes"]
            row["endurance"].append(entry)
    ordered = [days[key] for key in sorted(days)]

    def window(first: date, last: date) -> dict:
        rows = [r for r in ordered if first <= _d(r["date"]) <= last]
        methods = {e["method"] for r in rows for e in r["endurance"]}
        comparable = len(methods) == 1 and next(iter(methods)) not in {"duration_only", "invalid_power_input"}
        return {"strength_work_sets": sum(r["strength_work_sets"] for r in rows),
                "strength_tonnage_kg": _r(sum(r["strength_tonnage_kg"] for r in rows), 1),
                "endurance_minutes": _r(sum(r["endurance_minutes"] for r in rows), 1),
                "endurance_load": _r(sum(e["load"] for r in rows for e in r["endurance"]), 1) if comparable else None,
                "endurance_load_method": next(iter(methods)) if len(methods) == 1 else ("mixed_methods" if methods else None)}
    last7 = window(as_of - timedelta(days=6), as_of)
    prev28 = window(as_of - timedelta(days=34), as_of - timedelta(days=7))
    earliest = min((_d(s.date) for s in sessions), default=as_of)
    return {"daily": ordered, "last_7_days": last7, "previous_28_days": prev28,
            "previous_28_days_covered": (as_of - earliest).days >= 34,
            "note": "descriptive_totals_no_injury_or_readiness_claim"}


def _concurrent(sessions: List[SessionIn], as_of: date) -> List[dict]:
    flags = []
    recent = [s for s in sessions if 0 <= (as_of - _d(s.date)).days < 14]
    by_day: Dict[str, list] = defaultdict(list)
    for s in recent:
        by_day[s.date].append(s)
    for day in sorted(by_day):
        strength = [s for s in by_day[day] if s.type == "kracht"]
        endurance = [s for s in by_day[day] if s.type == "duur"]
        if not strength or not endurance:
            continue
        done = [ex for s in strength for ex in s.exercises if any(st.completedReps > 0 for st in ex.sets)]
        # The pooled evidence concerns lower-body explosive strength next to
        # cycling or running; explosive work for the upper body alone is not flagged.
        explosive = any(ex.power and ex.region != "upper" for ex in done)
        regions = {ex.region for ex in done}
        lower = True if regions & {"lower", "full"} else (None if "unknown" in regions or not regions else False)
        signed = [(a - b).total_seconds() / 3600 for a in map(_instant, strength) for b in map(_instant, endurance) if a and b]
        nearest = min(signed, key=abs) if signed else None
        gap = abs(nearest) if nearest is not None else None
        order = None if nearest is None else ("endurance_first" if nearest > 0 else "strength_first" if nearest < 0 else "simultaneous_start_times")
        if gap is None:
            code = "same_day_order_and_gap_unknown"
        elif gap < SAME_SESSION_HOURS:
            code = "explosive_work_within_3h_of_endurance" if explosive else "strength_within_3h_of_endurance"
        else:
            code = "same_day_separated_by_3h_or_more"
        flags.append({"date": day, "code": code, "gap_hours": _r(gap, 1), "order": order, "explosive_work": explosive,
                      "lower_body_strength_work": lower,
                      "evidence": "schumann_2022" if code.startswith("explosive") else "context_only"})
    return flags


def _concurrent_model(request: EngineRequest, sessions: List[SessionIn], as_of: date, endurance: dict) -> dict:
    from app.science.concurrent_service import concurrent_block   # imported late: that module uses helpers defined here
    return concurrent_block(request, sessions, as_of, endurance)


def evaluate(request: EngineRequest) -> dict:
    as_of = _d(request.asOfDate)
    unique = list({s.id: s for s in request.sessions}.values())   # exact repeats only; conflicts are refused by the contract
    sessions = [s for s in unique if _d(s.date) <= as_of]
    endurance = _endurance(request)
    return {
        "contract_version": CONTRACT_VERSION, "engine_version": ENGINE_VERSION,
        "as_of_date": request.asOfDate, "input_digest": input_digest(request),
        "sessions_used": len(sessions), "sessions_after_as_of_ignored": len(unique) - len(sessions),
        "duplicate_sessions_ignored": len(request.sessions) - len(unique),
        "strength": _strength(sessions, as_of), "endurance": endurance,
        "load": _load(sessions, as_of, endurance["reference"]["power_w"], endurance["reference"]["sport"]),
        "concurrent": _concurrent(sessions, as_of),
        "concurrent_model": _concurrent_model(request, sessions, as_of, endurance),
        "limitations": ["no_validated_readiness_score", "no_individual_interference_estimate",
                        "estimates_are_not_measurements", "parameters_not_empirically_validated"],
    }
