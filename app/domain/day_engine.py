"""
Day-level state engine for concurrent training (HARDENED - Sprint H1).

SPRINT H1: MODEL HARDENING & IDENTIFIABILITY
- Added capacity saturation: C_l update includes (1 - C_l/C_max_l) term
- Bound R_mito in [0,1] with enhanced Z2/HIIT updates and overload penalty
- All interference terms are explicit functions (no placeholders)
- Added T_legs structural/connective tissue state with slow tau (14-28d)
- T_legs guards heavy lower body work readiness

Maintains and updates daily states:
- Per-lift: D_l (fatigue), F_l (fitness), C_l (capacity, now with saturation)
- System: D_sys (system fatigue), R_mito (recovery capacity, bounded [0,1]), E_fat (endurance fatigue)
- Structural: T_legs (connective tissue fatigue, slow recovery)

Deterministic, pure Python domain logic.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
from datetime import date, timedelta

# Import canonical enums from single source of truth
from app.types import LiftType, EnduranceSport

# Backwards compatibility alias - EnduranceMode is deprecated, use EnduranceSport
EnduranceMode = EnduranceSport


@dataclass(frozen=True)
class DayEngineParams:
    """
    Configurable parameters for the day-level engine.
    
    All time constants in days.
    """
    # Strength impulse calculation
    alpha_I: float = 1.2  # Intensity exponent
    p_VL: float = 1.5  # Velocity loss penalty factor
    
    # System impulse weights (omega_l)
    omega: Dict[str, float] = field(default_factory=lambda: {
        'deadlift': 1.3,
        'squat': 1.1,
        'clean': 1.0,
        'bench': 0.7,
        'press': 0.7,
    })
    
    # Legs aggregate weights
    legs_weights: Dict[str, float] = field(default_factory=lambda: {
        'squat': 1.0,
        'deadlift': 1.2,
        'clean': 0.8,
    })
    
    # H1: Structural/connective tissue parameters
    tau_T_legs: float = 21.0  # Slow recovery for connective tissue (14-28d range)
    k_T_legs: float = 0.0002  # Tissue fatigue accumulation rate
    k_T_high_intensity: float = 0.0004  # Extra tissue cost for high intensity (>85%)
    T_legs_guardrail_threshold: float = 0.35  # Threshold for heavy legs guardrail
    
    # Time constants (days)
    tau_mito: float = 45.0
    tau_Efat: float = 3.0
    tau_sys: float = 3.0
    tau_Dl: Dict[str, float] = field(default_factory=lambda: {
        'deadlift': 5.0,
        'squat': 4.0,
        'clean': 3.0,
        'bench': 2.5,
        'press': 2.5,
    })
    tau_Fl: float = 21.0  # Same for all lifts in v1
    
    # Coefficients
    k_mito: float = 0.0008
    beta_sys: float = 0.20
    beta_l: Dict[str, float] = field(default_factory=lambda: {
        'squat': 0.25,
        'deadlift': 0.25,
        'clean': 0.25,
        'bench': 0.15,
        'press': 0.15,
    })
    k_Dl: float = 0.0005
    k_sys: float = 0.00025
    k_EHIIT: float = 0.0007
    k_SE: float = 0.00012  # Strength-to-endurance coupling
    k_Fl: float = 0.00008
    
    # Capacity update (H1: added saturation)
    g_l: float = 0.015  # Fitness contribution to capacity
    h_l: float = 0.010  # Fatigue reduction of capacity
    lambda_l: float = 0.0  # Detraining (v1: none)
    C_min: float = 20.0  # Minimum capacity floor
    C_max: float = 200.0  # H1: Maximum capacity ceiling (saturation)
    capacity_saturation_alpha: float = 1.0  # H1: Saturation curve steepness
    
    # H1: Enhanced R_mito parameters
    k_mito_z2: float = 0.0010  # R_mito gain from Z2 (separate from HIIT)
    k_mito_hiit: float = 0.0003  # R_mito gain from HIIT (smaller)
    k_mito_decay: float = 0.02  # R_mito decay rate
    k_mito_overload: float = 0.0005  # R_mito penalty from overload
    R_mito_max: float = 1.0  # H1: Hard upper bound
    R_mito_min: float = 0.0  # H1: Hard lower bound
    
    # Interference coefficients (H1: all explicit, no placeholders)
    k_ES_l: Dict[str, float] = field(default_factory=lambda: {
        'deadlift': 0.00035,
        'squat': 0.00030,
        'clean': 0.00028,
        'bench': 0.00008,
        'press': 0.00008,
    })
    k_ES_sys: float = 0.00018
    
    # Mode factors for interference
    mode_factors: Dict[str, float] = field(default_factory=lambda: {
        'running': 1.3,
        'cycling': 1.0,
        'swimming': 0.6,
    })
    
    # Priming
    priming_gain: float = 0.15
    priming_window_hours: float = 36.0
    
    # Readiness calculation
    w_sys: float = 0.5  # Weight of system fatigue in per-lift readiness
    
    def get_tau_Dl(self, lift: str) -> float:
        """Get fatigue time constant for a lift."""
        return self.tau_Dl.get(lift, 3.0)
    
    def get_beta_l(self, lift: str) -> float:
        """Get R_mito sensitivity for a lift."""
        return self.beta_l.get(lift, 0.20)
    
    def get_omega(self, lift: str) -> float:
        """Get system impulse weight for a lift."""
        return self.omega.get(lift, 1.0)
    
    def get_k_ES(self, lift: str) -> float:
        """Get interference coefficient for a lift."""
        return self.k_ES_l.get(lift, 0.0002)
    
    def get_mode_factor(self, mode: str) -> float:
        """Get interference mode factor."""
        return self.mode_factors.get(mode, 1.0)


@dataclass
class SetImpulse:
    """Impulse computed from a single strength set."""
    lift: str
    tonnage: float
    intensity: float  # I = load / C_l
    velocity_factor: float  # V = mean(v_ref/v_obs)
    vl: float  # Velocity loss
    reps: int
    avg_intensity_pct: float = 0.0  # H1: Average %1RM for tissue fatigue


@dataclass
class StrengthImpulses:
    """Aggregated impulses from all strength sets on a day."""
    per_lift: Dict[str, float]  # u_l per lift
    u_sys: float  # System impulse
    u_legs: float  # Legs aggregate
    u_met: float  # Metabolic strength impulse
    u_legs_high_intensity: float  # H1: High intensity legs impulse for T_legs
    sets: List[SetImpulse]  # Raw set data


@dataclass
class EnduranceImpulses:
    """Impulses from endurance sessions."""
    u_E_Z2: float  # Z2 component
    u_E_HIIT: float  # HIIT component
    u_E_total: float  # Total
    mode: str  # running/cycling/swimming
    has_HIIT: bool
    has_Z2: bool


@dataclass
class DailyImpulses:
    """All impulses for a single day."""
    strength: StrengthImpulses
    endurance: EnduranceImpulses
    date: date


@dataclass
class PerLiftState:
    """State for a single lift."""
    D_l: float = 0.0  # Fatigue (0-1+)
    F_l: float = 1.0  # Fitness/adaptation (0+)
    C_l: float = 100.0  # Capacity/e1RM-like (kg)


@dataclass
class DayState:
    """Full day state for an athlete (H1: added T_legs)."""
    date: date
    per_lift: Dict[str, PerLiftState] = field(default_factory=dict)
    D_sys: float = 0.0  # System fatigue (0-1+)
    R_mito: float = 0.0  # Recovery capacity (0-1, H1: now bounded)
    E_fat: float = 0.0  # Endurance fatigue (0-1+)
    T_legs: float = 0.0  # H1: Structural/connective tissue fatigue (0-1+)
    
    def get_lift(self, lift: str) -> PerLiftState:
        """Get or create per-lift state."""
        if lift not in self.per_lift:
            self.per_lift[lift] = PerLiftState()
        return self.per_lift[lift]


@dataclass
class ReadinessOutput:
    """Readiness scores with explanations."""
    per_lift: Dict[str, float]  # 0-1 scale
    endurance: float  # 0-1 scale
    overall: float  # Weighted average
    legs_structural: float  # H1: T_legs readiness for heavy lower
    explanations: List[str]


def compute_strength_impulses(
    sets: List[SetImpulse],
    params: DayEngineParams
) -> StrengthImpulses:
    """
    Compute daily strength impulses from rep_engine set outputs.
    
    Args:
        sets: List of SetImpulse from rep_engine outputs
        params: Engine parameters
    
    Returns:
        Aggregated StrengthImpulses
    """
    per_lift: Dict[str, float] = {}
    u_sys = 0.0
    u_legs = 0.0
    u_met = 0.0
    u_legs_high_intensity = 0.0  # H1: For T_legs
    
    for s in sets:
        # Fatigue cost factor: P = 1 + p_VL * VL
        P = 1.0 + params.p_VL * s.vl
        
        # Intensity factor: I^alpha_I
        I_factor = s.intensity ** params.alpha_I
        
        # Set impulse
        u_set = s.tonnage * I_factor * s.velocity_factor * P
        
        # Per-lift aggregate
        per_lift[s.lift] = per_lift.get(s.lift, 0.0) + u_set
        
        # System impulse contribution
        omega = params.get_omega(s.lift)
        u_sys += omega * u_set
        
        # Legs aggregate
        if s.lift in params.legs_weights:
            u_legs += params.legs_weights[s.lift] * u_set
            
            # H1: High intensity sets (>85%) contribute more to T_legs
            if s.avg_intensity_pct > 0.85:
                u_legs_high_intensity += params.legs_weights[s.lift] * u_set * (
                    (s.avg_intensity_pct - 0.85) / 0.15  # Scale 0-1 based on how far above 85%
                )
        
        # Metabolic impulse (simple: all high-rep sets count)
        if s.reps >= 8:
            u_met += s.tonnage * (1.0 + 0.5 * s.vl)
    
    return StrengthImpulses(
        per_lift=per_lift,
        u_sys=u_sys,
        u_legs=u_legs,
        u_met=u_met,
        u_legs_high_intensity=u_legs_high_intensity,  # H1
        sets=sets
    )


def compute_endurance_impulses(
    sessions: List[Tuple[str, float, str]],  # (mode, duration_or_tss, intensity_type)
    params: DayEngineParams
) -> EnduranceImpulses:
    """
    Compute endurance impulses from session data.
    
    Args:
        sessions: List of (mode, u_E_total, intensity_type) tuples
                 where intensity_type is 'z2', 'hiit', or 'mixed'
        params: Engine parameters
    
    Returns:
        EnduranceImpulses
    """
    u_E_Z2 = 0.0
    u_E_HIIT = 0.0
    u_E_total = 0.0
    dominant_mode = "cycling"  # Default
    has_HIIT = False
    has_Z2 = False
    
    for mode, u_E, intensity in sessions:
        u_E_total += u_E
        
        if intensity == 'z2':
            u_E_Z2 += u_E
            has_Z2 = True
        elif intensity == 'hiit':
            u_E_HIIT += u_E
            has_HIIT = True
            dominant_mode = mode
        elif intensity == 'mixed':
            # Split 30/70 for mixed
            u_E_Z2 += 0.3 * u_E
            u_E_HIIT += 0.7 * u_E
            has_Z2 = True
            has_HIIT = True
    
    return EnduranceImpulses(
        u_E_Z2=u_E_Z2,
        u_E_HIIT=u_E_HIIT,
        u_E_total=u_E_total,
        mode=dominant_mode,
        has_HIIT=has_HIIT,
        has_Z2=has_Z2
    )


def compute_interference(
    endurance: EnduranceImpulses,
    params: DayEngineParams,
    timing_factor: float = 1.0
) -> Tuple[Dict[str, float], float]:
    """
    H1: Compute interference from endurance to strength (all explicit terms).
    
    Returns:
        Tuple of (per_lift_interference, system_interference)
    """
    if not endurance.has_HIIT or endurance.u_E_HIIT <= 0:
        # H1: Explicit - return zero interference, not placeholder
        return ({lift: 0.0 for lift in params.omega.keys()}, 0.0)
    
    mode_factor = params.get_mode_factor(endurance.mode)
    
    # H1: Explicit interference calculation
    # Interference = k_ES * u_E_HIIT * mode_factor * timing_factor
    base_interf = endurance.u_E_HIIT * mode_factor * timing_factor
    
    # Per-lift interference (explicit coefficients)
    per_lift = {}
    for lift in params.omega.keys():
        k_ES = params.get_k_ES(lift)
        per_lift[lift] = k_ES * base_interf
    
    # System interference (explicit coefficient)
    sys_interf = params.k_ES_sys * base_interf
    
    return (per_lift, sys_interf)


def update_R_mito(
    current_R: float,
    impulses: EnduranceImpulses,
    overload_indicator: float,
    params: DayEngineParams
) -> float:
    """
    H1: Update R_mito with bounded [0,1], Z2/HIIT split, and overload penalty.
    
    R_mito update rules:
    - Base decay: R * exp(-decay_rate)
    - Z2 gain: +k_mito_z2 * u_E_Z2 (builds recovery capacity)
    - HIIT gain: +k_mito_hiit * u_E_HIIT (smaller, acute)
    - Overload penalty: -k_mito_overload * overload_indicator
    - Hard bounds: [R_mito_min, R_mito_max]
    
    Args:
        current_R: Current R_mito value
        impulses: Endurance impulses
        overload_indicator: 1.0 if overload detected, 0.0 otherwise
        params: Engine parameters
    
    Returns:
        New R_mito value (bounded [0,1])
    """
    # Base decay
    R_new = current_R * math.exp(-params.k_mito_decay)
    
    # Z2 contribution (builds mitochondrial capacity)
    R_new += params.k_mito_z2 * impulses.u_E_Z2
    
    # HIIT contribution (acute, smaller)
    R_new += params.k_mito_hiit * impulses.u_E_HIIT
    
    # Overload penalty
    R_new -= params.k_mito_overload * overload_indicator
    
    # H1: Hard bounds [0, 1]
    return max(params.R_mito_min, min(params.R_mito_max, R_new))


def update_capacity_with_saturation(
    current_C: float,
    F_l: float,
    D_l: float,
    params: DayEngineParams
) -> float:
    """
    H1: Update capacity with saturation term preventing divergence.
    
    C_new = C + g_l * F_l * (1 - C/C_max)^alpha - h_l * D_l - lambda_l
    
    The saturation term (1 - C/C_max)^alpha ensures:
    - Near C_max: diminishing returns (hard to increase further)
    - Far from C_max: normal adaptation
    - Prevents unbounded growth
    
    Args:
        current_C: Current capacity
        F_l: Fitness level
        D_l: Fatigue level
        params: Engine parameters
    
    Returns:
        New capacity value
    """
    # Saturation factor: (1 - C/C_max)^alpha
    # As C approaches C_max, this goes to 0
    saturation_ratio = max(0.0, min(1.0, current_C / params.C_max))
    saturation_factor = (1.0 - saturation_ratio) ** params.capacity_saturation_alpha
    
    # Fitness contribution with saturation
    fitness_contrib = params.g_l * F_l * saturation_factor
    
    # Fatigue reduction
    fatigue_contrib = params.h_l * D_l
    
    # Detraining
    detraining = params.lambda_l
    
    # Update with floor
    C_new = current_C + fitness_contrib - fatigue_contrib - detraining
    
    return max(params.C_min, C_new)


def update_T_legs(
    current_T: float,
    impulses: StrengthImpulses,
    params: DayEngineParams
) -> float:
    """
    H1: Update connective tissue fatigue with slow recovery.
    
    T_legs represents structural fatigue in legs (tendons, ligaments, fascia).
    - Updates slowly (tau 14-28 days)
    - Accumulates from high-intensity legs work
    - Decays exponentially
    
    Args:
        current_T: Current T_legs value
        impulses: Strength impulses
        params: Engine parameters
    
    Returns:
        New T_legs value
    """
    # Exponential decay
    T_new = current_T * math.exp(-1.0 / params.tau_T_legs)
    
    # Accumulation from high-intensity legs work
    T_new += params.k_T_legs * impulses.u_legs
    T_new += params.k_T_high_intensity * impulses.u_legs_high_intensity
    
    return max(0.0, min(1.0, T_new))


def update_day_state(
    current: DayState,
    impulses: DailyImpulses,
    params: DayEngineParams,
    has_priming: bool = False
) -> DayState:
    """
    H1: Update day state with hardened model.
    
    Key changes:
    - R_mito bounded [0,1] with Z2/HIIT split and overload penalty
    - Capacity update includes saturation term
    - T_legs tracking for structural fatigue
    - All interference terms explicit
    
    Args:
        current: Current day state
        impulses: Daily impulses
        params: Engine parameters
        has_priming: Whether Z2 priming is active
    
    Returns:
        Updated DayState
    """
    # H1: Detect overload condition (excessive HIIT + strength)
    overload_indicator = 1.0 if (
        impulses.endurance.u_E_HIIT > 50 and impulses.strength.u_sys > 30
    ) else 0.0
    
    # H1: Update R_mito with bounded model
    new_R_mito = update_R_mito(
        current.R_mito,
        impulses.endurance,
        overload_indicator,
        params
    )
    
    # Prior fatigue decays using only prior recovery history, not the current
    # day's endurance impulse. Newly added load has no retroactive effect.
    decayed = decay_day_state_to_date(current, current.date + timedelta(days=1), params)
    R = new_R_mito
    if impulses.strength.u_sys == 0 and impulses.endurance.u_E_total == 0 and not any(impulses.strength.per_lift.values()):
        decayed.date = current.date
        return decayed
    
    # Compute interference (explicit terms only)
    interf_per_lift, interf_sys = compute_interference(impulses.endurance, params)
    
    # H1: Update T_legs structural fatigue
    new_T_legs = update_T_legs(current.T_legs, impulses.strength, params)
    
    # Create new state (same date - caller manages date transitions)
    new_state = DayState(
        date=current.date,
        per_lift={},
        D_sys=0.0,  # Will compute below
        R_mito=new_R_mito,
        E_fat=0.0,   # Will compute below
        T_legs=new_T_legs  # H1
    )
    
    # Per-lift updates
    for lift in dict.fromkeys([*current.per_lift, *impulses.strength.per_lift]):
        current_lift = current.per_lift.get(lift, PerLiftState())
        
        # Fatigue update
        tau_eff = params.get_tau_Dl(lift) / (1.0 + params.get_beta_l(lift) * R)
        D_new = decayed.per_lift.get(lift, PerLiftState()).D_l
        D_new += params.k_Dl * impulses.strength.per_lift.get(lift, 0.0)
        D_new += interf_per_lift.get(lift, 0.0)
        
        # Fitness update with optional priming
        F_new = current_lift.F_l * math.exp(-1.0 / params.tau_Fl)
        priming = 1.0 + params.priming_gain if has_priming else 1.0
        F_new += params.k_Fl * impulses.strength.per_lift.get(lift, 0.0) * priming
        
        # H1: Capacity update with saturation
        C_new = update_capacity_with_saturation(
            current_lift.C_l,
            F_new,
            D_new,
            params
        )
        
        new_state.per_lift[lift] = PerLiftState(
            D_l=max(0.0, D_new),
            F_l=max(0.0, F_new),
            C_l=C_new
        )
    
    # System fatigue update
    tau_sys_eff = params.tau_sys / (1.0 + params.beta_sys * R)
    D_sys_new = decayed.D_sys
    D_sys_new += params.k_sys * impulses.strength.u_sys
    D_sys_new += interf_sys
    new_state.D_sys = max(0.0, D_sys_new)
    
    # Endurance fatigue update
    E_fat_new = current.E_fat * math.exp(-1.0 / params.tau_Efat)
    E_fat_new += params.k_EHIIT * impulses.endurance.u_E_total  # Easy work also has a load cost
    E_fat_new += params.k_SE * impulses.strength.u_legs
    new_state.E_fat = max(0.0, E_fat_new)
    
    return new_state


def decay_day_state_to_date(
    current: DayState,
    target_date: date,
    params: DayEngineParams
) -> DayState:
    """
    Decay day state forward to target date with no new impulses.
    
    This handles day-to-day carryover when there are no sessions.
    Each day decays exponentially according to the model time constants.
    
    Args:
        current: Starting day state
        target_date: Date to decay to (must be >= current.date)
        params: Engine parameters
    
    Returns:
        New DayState with decayed values and target_date
    """
    if target_date < current.date:
        raise ValueError(f"target_date {target_date} must be >= current.date {current.date}")
    
    days_diff = (target_date - current.date).days
    if days_diff == 0:
        # Return a copy with same date
        return DayState(
            date=target_date,
            per_lift={
                lift: PerLiftState(D_l=s.D_l, F_l=s.F_l, C_l=s.C_l)
                for lift, s in current.per_lift.items()
            },
            D_sys=current.D_sys,
            R_mito=current.R_mito,
            E_fat=current.E_fat,
            T_legs=current.T_legs
        )
    
    # Create new state for target date
    new_state = DayState(
        date=target_date,
        per_lift={},
        D_sys=0.0,
        R_mito=0.0,
        E_fat=0.0,
        T_legs=0.0
    )
    
    # Integral of the decaying recovery proxy over this interval; ensures
    # splitting a rest-day interval does not change the resulting fatigue.
    rate = params.k_mito_decay
    integrated_R = current.R_mito * (-math.expm1(-rate * days_diff)) / rate if rate else current.R_mito * days_diff
    # Decay per-lift states
    for lift, lift_state in current.per_lift.items():
        # Fatigue decay over days_diff
        D_new = lift_state.D_l * math.exp(-(days_diff + params.get_beta_l(lift) * integrated_R) / params.get_tau_Dl(lift))
        # Fitness decay
        F_new = lift_state.F_l * math.exp(-days_diff / params.tau_Fl)
        # Capacity stays (it's a baseline, doesn't decay quickly)
        C_new = max(params.C_min, lift_state.C_l - params.lambda_l * days_diff)
        
        new_state.per_lift[lift] = PerLiftState(D_l=D_new, F_l=F_new, C_l=C_new)
    
    # System fatigue decay
    new_state.D_sys = current.D_sys * math.exp(-(days_diff + params.beta_sys * integrated_R) / params.tau_sys)
    
    # R_mito decay
    new_state.R_mito = current.R_mito * math.exp(-days_diff * params.k_mito_decay)
    
    # E_fat decay
    new_state.E_fat = current.E_fat * math.exp(-days_diff / params.tau_Efat)
    
    # T_legs decay (slow)
    new_state.T_legs = current.T_legs * math.exp(-days_diff / params.tau_T_legs)
    
    return new_state


def compute_readiness(
    state: DayState,
    params: DayEngineParams
) -> ReadinessOutput:
    """
    H1: Compute readiness scores including T_legs guardrail.
    
    Args:
        state: Current day state
        params: Engine parameters
    
    Returns:
        ReadinessOutput with scores and explanations
    """
    per_lift = {}
    explanations = []
    
    # H1: Legs structural readiness
    # T_legs > threshold reduces readiness for heavy lower body
    legs_structural_ready = max(0.0, 1.0 - state.T_legs / params.T_legs_guardrail_threshold)
    
    # Per-lift readiness
    for lift, lift_state in state.per_lift.items():
        # Base readiness
        readiness = 1.0 - lift_state.D_l - params.w_sys * state.D_sys
        
        # H1: Apply legs structural guardrail for lower body lifts
        if lift in ['squat', 'deadlift', 'clean', 'power_clean']:
            # Heavy legs work readiness is gated by structural state
            readiness = min(readiness, legs_structural_ready)
        
        per_lift[lift] = max(0.0, min(1.0, readiness))
    
    # Endurance readiness
    endurance_ready = max(0.0, min(1.0, 1.0 - state.E_fat))
    
    # Overall (weighted average)
    if per_lift:
        overall = sum(per_lift.values()) / len(per_lift)
        overall = 0.7 * overall + 0.3 * endurance_ready
    else:
        overall = endurance_ready
    
    # Generate explanations
    if state.D_sys > 0.4:
        explanations.append("System fatigue high - consider lighter session")
    
    if state.R_mito > 0.5:
        explanations.append("Aerobic exposure proxy elevated; recovery benefit is unvalidated")
    elif state.R_mito < 0.2:
        explanations.append("Limited recorded aerobic exposure; mitochondrial capacity is not measured")
    
    if state.E_fat > 0.3:
        explanations.append("Endurance fatigue elevated - monitor HIIT volume")
    
    # H1: T_legs explanation
    if state.T_legs > params.T_legs_guardrail_threshold:
        explanations.append("Accumulated leg-load proxy high - review heavy lower body work")
    elif state.T_legs > 0.5 * params.T_legs_guardrail_threshold:
        explanations.append("Accumulated leg-load proxy building - monitor heavy work")
    
    # Per-lift explanations
    for lift, lift_state in state.per_lift.items():
        if lift_state.D_l > 0.4:
            explanations.append(f"{lift}: local fatigue elevated")
        # H1: Capacity saturation note
        saturation_ratio = lift_state.C_l / params.C_max
        if saturation_ratio > 0.9:
            explanations.append(f"{lift}: approaching capacity ceiling")
    
    if not explanations:
        explanations.append("Readiness neutral - train as planned")
    
    return ReadinessOutput(
        per_lift=per_lift,
        endurance=endurance_ready,
        overall=overall,
        legs_structural=legs_structural_ready,  # H1
        explanations=explanations[:5]  # Max 5 explanations
    )


def simulate_day_transition(
    current_state: DayState,
    strength_sets: List[SetImpulse],
    endurance_sessions: List[Tuple[str, float, str]],
    params: Optional[DayEngineParams] = None,
    has_priming: bool = False
) -> Tuple[DayState, DailyImpulses, ReadinessOutput]:
    """
    H1: Main entry point - simulate one day transition with hardened model.
    
    Args:
        current_state: State at start of day
        strength_sets: List of strength set impulses
        endurance_sessions: List of (mode, u_E, intensity) tuples
        params: Optional parameter override
        has_priming: Whether priming is active
    
    Returns:
        Tuple of (new_state, impulses, readiness)
    """
    params = params or DayEngineParams()
    
    # Compute impulses
    strength_impulses = compute_strength_impulses(strength_sets, params)
    endurance_impulses = compute_endurance_impulses(endurance_sessions, params)
    
    impulses = DailyImpulses(
        strength=strength_impulses,
        endurance=endurance_impulses,
        date=current_state.date
    )
    
    # Update state
    new_state = update_day_state(current_state, impulses, params, has_priming)
    
    # Compute readiness
    readiness = compute_readiness(new_state, params)
    
    return new_state, impulses, readiness


def create_initial_state(
    start_date: date,
    lifts: List[str],
    default_C: float = 100.0
) -> DayState:
    """
    Create initial state for an athlete.
    
    Args:
        start_date: Starting date
        lifts: List of lifts to track
        default_C: Default capacity per lift
    
    Returns:
        Initialized DayState
    """
    per_lift = {}
    for lift in lifts:
        per_lift[lift] = PerLiftState(
            D_l=0.0,
            F_l=1.0,
            C_l=default_C
        )
    
    return DayState(
        date=start_date,
        per_lift=per_lift,
        D_sys=0.0,
        R_mito=0.0,
        E_fat=0.0,
        T_legs=0.0  # H1
    )

