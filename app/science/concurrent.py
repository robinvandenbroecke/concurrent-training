"""Concurrent strength-endurance model: state, calibration, forecast, planning.

Replaces the legacy three-compartment model (app.domain) as the candidate
model. Design rules, each a direct answer to a defect of the old model:

* One equation per domain, in log performance, algebraic in its states:

      strength (region r):  y = level + a*G_r - b*F_r - k*E_r - i*X_r + noise
      endurance:            y = level + a*G_e - b*F_e - k*S_l + t*T   + noise

  G = slow "fitness" trace of the own-domain dose, F = fast "fatigue" trace,
  E_r / S_l = fatigue trace of the OTHER domain acting on the same region
  (acute cross-fatigue), X = fitness trace of strength work done within 3 h
  of endurance work (attenuated adaptation), T = fitness-like trace of
  lower-body strength work (positive transfer to endurance). Fatigue never
  subtracts permanently from a capacity (old defect LEG-03).
* Doses are dimensionless and relative: work sets and threshold-relative
  minutes, not kilograms (old defect LEG-04). A typical session is about 1.
* Traces decay exactly in continuous time between real session instants, so
  the result does not depend on how time is cut up (old defect LEG-02).
* Given the time constants the model is LINEAR in its coefficients. They are
  estimated per athlete by Bayesian linear regression with weakly informative
  Gaussian priors and an estimated noise level. That yields, in closed form: posterior and
  predictive intervals, the share of each coefficient that the athlete's own
  data determined, and the marginal likelihood for nested comparison
  (level only -> own-domain dynamics -> cross-domain interaction).
* An interaction is reported as shown for THIS athlete only when the evidence
  and the out-of-sample error both favour it; otherwise the coefficients are
  labelled as group-level priors.

Evidence behind the structure (see MODEL_REGISTER.md for details and limits):
explosive and, in trained people, maximal lower-body strength gains are
attenuated mainly when both modes share a session and not when separated by
hours (Schumann 2022, doi:10.1007/s40279-021-01587-7; Petre 2021,
doi:10.1007/s40279-021-01426-9); a resistance session can impair endurance
performance for 24-72 h whereas a typical endurance session is recovered
within about a day (Doma 2017, doi:10.1007/s40279-017-0758-3); heavy strength
training improves running economy and time-trial performance (Llanos-Lagos
2024, doi:10.1007/s40279-023-01978-y and doi:10.1007/s40279-024-02018-z).
Fitness-fatigue models are poorly identified from training logs (Marchal 2025,
doi:10.1038/s41598-025-88153-7), which is why identifiability is measured and
reported here instead of assumed.

Prior magnitudes are order-of-magnitude statements, NOT population estimates.
Nothing in this module has been validated on real athletes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import itertools
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.science.load_velocity import t_critical_95

MODEL_VERSION = "ct-concurrent-1.0.0"
SAME_SESSION_HOURS = 3.0
SETS_PER_DOSE_UNIT = 10.0          # ten work sets for one region = dose 1
MINUTES_PER_DOSE_UNIT = 60.0       # sixty minutes at the reference power = dose 1
MIN_OBSERVATIONS = 6
MIN_WALK_FORWARD_TESTS = 8
MAX_OBSERVATIONS = 400            # most recent per domain; older ones describe another athlete
MAX_WALK_FORWARD_TESTS = 150
LEVELS = ("level", "own", "cross")

# state vector layout
FS_L, FS_U, FE_L, FE_U, GS_L, GS_U, GX_L, GE, GT = range(9)


@dataclass(frozen=True)
class TimeConstants:
    """Days. Strength fatigue outlasts endurance fatigue (Doma 2017)."""
    fatigue_strength: float = 2.0
    fatigue_endurance: float = 1.0
    fitness_strength: float = 42.0
    fitness_endurance: float = 42.0

    def rates(self) -> np.ndarray:
        fs, fe, gs, ge = (1.0 / v for v in (self.fatigue_strength, self.fatigue_endurance,
                                             self.fitness_strength, self.fitness_endurance))
        return np.array([fs, fs, fe, fe, gs, gs, gs, ge, ge])


@dataclass(frozen=True)
class Event:
    """One training session as doses. ``t`` is wall-clock time in days."""
    t: float
    strength_lower: float = 0.0
    strength_upper: float = 0.0
    endurance_lower: float = 0.0     # running, cycling
    endurance_upper: float = 0.0     # swimming
    endurance_other: float = 0.0     # counts for endurance fitness only
    near_endurance: float = 0.0      # 1 if the strength work was within 3 h of endurance work, else 0

    def impulse(self) -> np.ndarray:
        e = self.endurance_lower + self.endurance_upper + self.endurance_other
        return np.array([self.strength_lower, self.strength_upper, self.endurance_lower, self.endurance_upper,
                         self.strength_lower, self.strength_upper, self.strength_lower * self.near_endurance,
                         e, self.strength_lower])


@dataclass(frozen=True)
class Observation:
    t: float
    series: str                      # one level (intercept) per series
    domain: str                      # "strength" | "endurance"
    region: str                      # "lower" | "upper"
    value: float                     # log performance
    noise_ratio: float = 1.0         # measurement noise relative to the domain's reference noise


# Priors: (mean, sd) of the effect on log performance per dose unit of the trace.
PRIORS = {
    "strength": {"noise_sd": 0.04,
                 "fitness": (0.004, 0.004), "fatigue": (0.04, 0.04),
                 "cross_fatigue": (0.02, 0.02), "interference": (0.001, 0.002)},
    "endurance": {"noise_sd": 0.03,
                  "fitness": (0.004, 0.004), "fatigue": (0.03, 0.03),
                  "cross_fatigue": (0.02, 0.02), "transfer": (0.0005, 0.001)},
}
TERMS = {"strength": ("fitness", "fatigue", "cross_fatigue", "interference"),
         "endurance": ("fitness", "fatigue", "cross_fatigue", "transfer")}
LEVEL_TERMS = {"level": 0, "own": 2, "cross": 4}
INTERCEPT_SD = 0.3
NOISE_PRIOR_WEIGHT = 4.0         # pseudo-observations behind the reference noise level


def mark_proximity(events: Sequence[Event], hours: float = SAME_SESSION_HOURS) -> List[Event]:
    """Set ``near_endurance`` from the actual gaps between sessions."""
    endurance_times = [e.t for e in events if e.endurance_lower + e.endurance_upper + e.endurance_other > 0]
    out = []
    for e in events:
        near = 0.0
        if e.strength_lower > 0 and any(abs(e.t - t) * 24.0 < hours for t in endurance_times):
            near = 1.0
        out.append(Event(e.t, e.strength_lower, e.strength_upper, e.endurance_lower, e.endurance_upper,
                         e.endurance_other, near))
    return out


def states_at(events: Sequence[Event], times: Sequence[float], constants: TimeConstants,
              initial: Optional[np.ndarray] = None, initial_time: Optional[float] = None) -> np.ndarray:
    """State just BEFORE each query time (a session at exactly that time is not yet included)."""
    rates = constants.rates()
    order = sorted(range(len(times)), key=lambda i: times[i])
    ordered_events = sorted(events, key=lambda e: e.t)
    state = np.zeros(9) if initial is None else np.array(initial, dtype=float)
    clock = initial_time
    out = np.zeros((len(times), 9))
    index = 0

    def advance(to: float):
        nonlocal state, clock
        if clock is not None:
            if to < clock - 1e-9:
                raise ValueError("time runs backwards")
            state = state * np.exp(-rates * max(0.0, to - clock))
        clock = to

    for i in order:
        while index < len(ordered_events) and ordered_events[index].t < times[i]:
            advance(ordered_events[index].t)
            state = state + ordered_events[index].impulse()
            index += 1
        advance(times[i])
        out[i] = state
    return out


def features(domain: str, region: str, state: np.ndarray) -> np.ndarray:
    """Signed regressors in the order of TERMS[domain]."""
    if domain == "strength":
        if region == "lower":
            return np.array([state[GS_L], -state[FS_L], -state[FE_L], -state[GX_L]])
        return np.array([state[GS_U], -state[FS_U], -state[FE_U], 0.0])
    return np.array([state[GE], -(state[FE_L] if region == "lower" else state[FE_U]), -state[FS_L], state[GT]])


@dataclass
class Fit:
    domain: str
    level: str
    series: Tuple[str, ...]
    mean: np.ndarray
    cov: np.ndarray                  # posterior covariance of the coefficients, absolute units
    sigma2: float                    # estimated observation noise variance (log units)
    df: int                          # degrees of freedom for interval limits
    prior_var: np.ndarray
    log_evidence: float
    n: int
    prior_only: bool = False

    @property
    def terms(self) -> Tuple[str, ...]:
        return TERMS[self.domain][: LEVEL_TERMS[self.level]]

    def coefficient(self, term: str) -> Tuple[float, float]:
        """(mean, standard deviation) of one shared coefficient; (0, 0) if not in this level."""
        if term not in self.terms:
            return 0.0, 0.0
        j = len(self.series) + self.terms.index(term)
        return float(self.mean[j]), math.sqrt(self.cov[j, j])

    def informed_by_data(self, term: str) -> Optional[float]:
        """1 - posterior variance / prior variance: 0 = the prior, 1 = fully determined by the data."""
        if term not in self.terms:
            return None
        j = len(self.series) + self.terms.index(term)
        return float(min(1.0, max(0.0, 1.0 - self.cov[j, j] / self.prior_var[j])))

    def row(self, series: str, x: np.ndarray) -> Optional[np.ndarray]:
        if series not in self.series:
            return None
        row = np.zeros(len(self.mean))
        row[self.series.index(series)] = 1.0
        k = LEVEL_TERMS[self.level]
        row[len(self.series): len(self.series) + k] = x[:k]
        return row

    def predict(self, series: str, x: np.ndarray, noise_ratio: float = 1.0) -> Optional[Tuple[float, float]]:
        """Predictive mean and standard deviation for a NEW observation of a known series."""
        row = self.row(series, x)
        if row is None:
            return None
        return float(row @ self.mean), math.sqrt(self.sigma2 * noise_ratio ** 2 + float(row @ self.cov @ row))

    def effect(self, x: np.ndarray, terms: Sequence[str]) -> Tuple[float, float]:
        """Mean and standard deviation of the summed contribution of some terms (no level, no noise)."""
        row = np.zeros(len(self.mean))
        for term in terms:
            if term in self.terms:
                j = self.terms.index(term)
                row[len(self.series) + j] = x[j]
        return float(row @ self.mean), math.sqrt(max(0.0, float(row @ self.cov @ row)))


def fit(domain: str, observations: Sequence[Observation], states: np.ndarray, level: str = "cross") -> Fit:
    """Bayesian linear regression with Gaussian priors in absolute units.

    The noise variance is estimated by a damped fixed point (residuals of the
    posterior mean, effective degrees of freedom, and NOISE_PRIOR_WEIGHT
    pseudo-observations at the reference noise). The coefficient priors do not
    scale with the noise: an athlete with clean measurements does not get
    tighter priors for free. ``states[i]`` belongs to ``observations[i]``.
    """
    prior = PRIORS[domain]
    sigma0 = prior["noise_sd"]
    series = tuple(sorted({o.series for o in observations}))
    terms = TERMS[domain][: LEVEL_TERMS[level]]
    p = len(series) + len(terms)
    m0, s0 = np.zeros(p), np.ones(p)
    for j, name in enumerate(series):
        values = sorted(o.value for o in observations if o.series == name)
        m0[j], s0[j] = values[len(values) // 2], INTERCEPT_SD
    for j, term in enumerate(terms):
        m0[len(series) + j], s0[len(series) + j] = prior[term]
    n = len(observations)
    X, y = np.zeros((n, p)), np.zeros(n)
    for i, o in enumerate(observations):
        X[i, series.index(o.series)] = 1.0
        X[i, len(series):] = features(domain, o.region, states[i])[: len(terms)]
        X[i] /= o.noise_ratio
        y[i] = o.value / o.noise_ratio
    precision0 = np.diag(1.0 / s0 ** 2)
    sigma2, cov, mean, edf = sigma0 ** 2, np.diag(s0 ** 2), m0.copy(), 0.0
    for _ in range(50 if n else 0):
        cov = np.linalg.inv(precision0 + X.T @ X / sigma2)
        mean = cov @ (precision0 @ m0 + X.T @ y / sigma2)
        residual = y - X @ mean
        edf = float(np.sum((X @ cov) * X)) / sigma2
        updated = (float(residual @ residual) + NOISE_PRIOR_WEIGHT * sigma0 ** 2) / (n - edf + NOISE_PRIOR_WEIGHT)
        if abs(updated - sigma2) < 1e-10 * sigma2:
            sigma2 = updated
            break
        sigma2 = updated
    if n:
        cov = np.linalg.inv(precision0 + X.T @ X / sigma2)
        mean = cov @ (precision0 @ m0 + X.T @ y / sigma2)
        # log N(y; X m0, sigma2 I + X S0 X'), by the determinant lemma and the Woodbury identity.
        centred = y - X @ m0
        projected = X.T @ centred
        logdet = n * math.log(sigma2) + np.linalg.slogdet(precision0 + X.T @ X / sigma2)[1] + float(np.sum(np.log(s0 ** 2)))
        quadratic = (float(centred @ centred) - float(projected @ cov @ projected) / sigma2) / sigma2
        evidence = -0.5 * (n * math.log(2 * math.pi) + logdet + quadratic)
        evidence -= sum(math.log(o.noise_ratio) for o in observations)
    else:
        evidence = 0.0
    df = max(1, int(n - edf + NOISE_PRIOR_WEIGHT))
    return Fit(domain, level, series, mean, cov, float(sigma2), df, s0 ** 2, float(evidence), n)


def prior_fit(domain: str) -> Fit:
    """The model before any data of this athlete: group-level priors only."""
    result = fit(domain, [], np.zeros((0, 9)), "cross")
    result.prior_only = True
    return result


def walk_forward(domain: str, observations: Sequence[Observation], states: np.ndarray,
                 minimum_train: int = MIN_OBSERVATIONS) -> dict:
    """Predict every observation from strictly earlier ones; compare with naive baselines."""
    order = sorted(range(len(observations)), key=lambda i: observations[i].t)
    errors: Dict[str, List[float]] = {name: [] for name in (*LEVELS, "last_observation")}
    covered = 0
    first = max(0, len(order) - MAX_WALK_FORWARD_TESTS)
    for position, i in enumerate(order):
        if position < first:
            continue
        target = observations[i]
        train = [j for j in order[:position] if observations[j].t < target.t]
        same = [j for j in train if observations[j].series == target.series]
        if len(train) < minimum_train or len(same) < 2:
            continue
        train_obs, train_states = [observations[j] for j in train], states[train]
        x = features(domain, target.region, states[i])
        inside = True
        for level in LEVELS:
            model = fit(domain, train_obs, train_states, level)
            mean, scale = model.predict(target.series, x, target.noise_ratio)
            errors[level].append(abs(target.value - mean))
            if level == "cross":
                inside = abs(target.value - mean) <= t_critical_95(model.df) * scale
        errors["last_observation"].append(abs(target.value - observations[same[-1]].value))
        covered += inside
    tests = len(errors["level"])
    return {"tests": tests,
            "mae": {name: (sum(v) / tests if tests else None) for name, v in errors.items()},
            "interval_coverage_95": (covered / tests if tests else None)}


def calibrate(domain: str, observations: Sequence[Observation], events: Sequence[Event],
              constants: TimeConstants) -> dict:
    """Fit the three nested levels and say honestly what the athlete's data support."""
    if len(observations) < MIN_OBSERVATIONS:
        return {"status": "prior_only", "fit": prior_fit(domain), "observations": len(observations),
                "reason": "fewer_than_6_performance_observations"}
    observations = sorted(observations, key=lambda o: o.t)[-MAX_OBSERVATIONS:]
    states = states_at(events, [o.t for o in observations], constants)
    fits = {level: fit(domain, observations, states, level) for level in LEVELS}
    forward = walk_forward(domain, observations, states)
    evidence = {level: fits[level].log_evidence for level in LEVELS}
    enough = forward["tests"] >= MIN_WALK_FORWARD_TESTS
    mae = forward["mae"]

    def supported(better: str, simpler: str) -> bool:
        # Bayes factor above 3 AND a lower out-of-sample error: both, never one alone.
        return bool(enough and evidence[better] - evidence[simpler] > math.log(3.0) and mae[better] < mae[simpler])

    own = supported("own", "level")
    cross = supported("cross", "own")
    beats_naive = bool(enough and min(mae[level] for level in LEVELS) < 0.9 * mae["last_observation"])
    return {"status": "ok", "fit": fits["cross"], "fits": fits, "observations": len(observations),
            "log_evidence": evidence, "walk_forward": forward,
            "own_dynamics_supported": own, "interaction_supported": cross,
            "beats_last_observation": beats_naive,
            "verdict": ("interaction_shown_in_own_data" if cross else "own_dynamics_shown_in_own_data" if own
                        else "not_enough_tests" if not enough else "not_shown_in_own_data")}


def select_time_constants(strength: Sequence[Observation], endurance: Sequence[Observation], events: Sequence[Event],
                          default: TimeConstants = TimeConstants()) -> Tuple[TimeConstants, dict]:
    """Keep the defaults unless the data clearly prefer other fatigue time constants (Bayes factor > 20)."""
    def evidence(constants: TimeConstants) -> float:
        total = 0.0
        for domain, observations in (("strength", strength), ("endurance", endurance)):
            if len(observations) >= MIN_OBSERVATIONS:
                total += fit(domain, observations, states_at(events, [o.t for o in observations], constants), "cross").log_evidence
        return total
    if len(strength) < 2 * MIN_OBSERVATIONS and len(endurance) < 2 * MIN_OBSERVATIONS:
        return default, {"source": "defaults", "reason": "too_few_observations_to_compare"}
    base = evidence(default)
    best, best_value = default, base
    for fs, fe in itertools.product((1.0, 2.0, 3.0), (0.5, 1.0, 2.0)):
        candidate = TimeConstants(fs, fe, default.fitness_strength, default.fitness_endurance)
        value = evidence(candidate)
        if value > best_value:
            best, best_value = candidate, value
    if best_value - base > math.log(20.0):
        return best, {"source": "selected_by_evidence", "log_bayes_factor_vs_default": best_value - base}
    return default, {"source": "defaults", "reason": "data_do_not_discriminate",
                     "largest_log_bayes_factor": best_value - base}


# ── forecast and planning ───────────────────────────────────────────────────

@dataclass(frozen=True)
class PlannedSession:
    label: str
    domain: str                      # "strength" | "endurance"
    region: str                      # strength: lower | upper | full ; endurance: lower | upper
    dose: float
    key: bool = False

    def event(self, t: float) -> Event:
        if self.domain == "endurance":
            return Event(t, endurance_lower=self.dose if self.region != "upper" else 0.0,
                         endurance_upper=self.dose if self.region == "upper" else 0.0)
        return Event(t, strength_lower=self.dose if self.region in {"lower", "full"} else 0.0,
                     strength_upper=self.dose if self.region == "upper" else 0.5 * self.dose if self.region == "full" else 0.0)

    def target_region(self) -> str:
        return "upper" if self.region == "upper" else "lower"


def readiness(fit_: Fit, domain: str, region: str, state: np.ndarray) -> Tuple[float, float]:
    """Fatigue-related part of log performance (own + cross), <= 0 when fresh is the reference."""
    return fit_.effect(features(domain, region, state), ("fatigue", "cross_fatigue"))


def percent(log_effect: float) -> float:
    return 100.0 * math.expm1(log_effect)


def evaluate_schedule(fits: Dict[str, Fit], state: np.ndarray, start: float, schedule: Sequence[Tuple[float, PlannedSession]],
                      constants: TimeConstants, horizon_end: float, weights: Dict[str, float]) -> dict:
    """Predicted freshness at every planned session and the state at the end of the horizon."""
    events = mark_proximity([session.event(t) for t, session in schedule])
    times = [t for t, _ in schedule] + [horizon_end]
    states = states_at(events, times, constants, initial=state, initial_time=start)
    rows, score = [], 0.0
    for (t, session), event, s in zip(schedule, events, states):
        mean, scale = readiness(fits[session.domain], session.domain, session.target_region(), s)
        limit = t_critical_95(fits[session.domain].df) * scale
        rows.append({"label": session.label, "t": t, "domain": session.domain, "key": session.key,
                     "readiness_pct": percent(mean), "readiness_low_pct": percent(mean - limit),
                     "readiness_high_pct": percent(mean + limit),
                     "within_3h_of_endurance": bool(event.near_endurance)})
        score += weights[session.domain] * (2.0 if session.key else 1.0) * mean
    end = {}
    for domain, region in (("strength", "lower"), ("strength", "upper"), ("endurance", "lower")):
        x_end = features(domain, region, states[-1])
        x_start = features(domain, region, state)
        adaptation, _ = fits[domain].effect(x_end - x_start, ("fitness", "interference", "transfer"))
        fatigue, _ = readiness(fits[domain], domain, region, states[-1])
        name = f"{domain}_{region}" if domain == "strength" else "endurance"
        end[name] = {"adaptation_change_pct": percent(adaptation), "fatigue_pct": percent(fatigue)}
        if region == "lower":
            score += weights[domain] * (adaptation + fatigue)
    return {"score": score, "sessions": rows, "end_of_horizon": end}


def suggest_week(fits: Dict[str, Fit], state: np.ndarray, start: float, sessions: Sequence[PlannedSession],
                 slots: Sequence[float], constants: TimeConstants, horizon_end: float, weights: Dict[str, float],
                 top: int = 3, exact_limit: int = 20000) -> dict:
    """Place sessions on free slots so that weighted freshness and end state are best.

    Exhaustive when the number of arrangements is small, otherwise a
    deterministic improvement search from an even spread (then "heuristic").
    """
    slots = sorted(slots)
    k = len(sessions)
    if k == 0 or k > len(slots):
        raise ValueError("need between one session and one session per free slot")

    def value(assignment: Tuple[int, ...]) -> dict:
        schedule = sorted(((slots[slot], session) for slot, session in zip(assignment, sessions)), key=lambda item: item[0])
        return evaluate_schedule(fits, state, start, schedule, constants, horizon_end, weights)

    count = math.perm(len(slots), k)
    results: Dict[Tuple[int, ...], dict] = {}
    if count <= exact_limit:
        method = "exhaustive"
        for assignment in itertools.permutations(range(len(slots)), k):
            results[assignment] = value(assignment)
    else:
        method = "heuristic"
        import random
        rng = random.Random(len(slots) * 1000 + k)          # fixed seed: same input, same answer
        step = len(slots) / k
        starts = [tuple(int(i * step) for i in range(k))] + [tuple(rng.sample(range(len(slots)), k)) for _ in range(11)]
        for current in starts:
            results.setdefault(current, value(current))
            improved = True
            while improved and len(results) < exact_limit:
                improved = False
                for i in range(k):
                    for slot in range(len(slots)):
                        candidate = list(current)
                        if slot in candidate:
                            j = candidate.index(slot)
                            candidate[i], candidate[j] = candidate[j], candidate[i]
                        else:
                            candidate[i] = slot
                        candidate = tuple(candidate)
                        if candidate not in results:
                            results[candidate] = value(candidate)
                        if results[candidate]["score"] > results[current]["score"] + 1e-12:
                            current, improved = candidate, True
    ranked = sorted(results.items(), key=lambda item: (-item[1]["score"], item[0]))
    unique, seen = [], set()
    for assignment, result in ranked:
        signature = tuple(sorted((round(slots[slot], 6), session.label) for slot, session in zip(assignment, sessions)))
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(result)
        if len(unique) == top:
            break
    worst = ranked[-1][1]["score"]
    return {"method": method, "arrangements_evaluated": len(results), "best": unique,
            "spread_log_score": unique[0]["score"] - worst}
