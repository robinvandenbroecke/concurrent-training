"""
Day-level state engine for concurrent training.

Maintains and updates daily states:
- Per-lift: D_l (fatigue), F_l (fitness), C_l (capacity)
- System: D_sys (system fatigue), R_mito (recovery capacity), E_fat (endurance fatigue)

Deterministic, pure Python domain logic.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
from datetime import date, timedelta
from enum import Enum


class LiftType(str, Enum):
    """Standard lift types."""
    SQUAT = "squat"
    BENCH = "bench"
    DEADLIFT = "deadlift"
    PRESS = "press"
    CLEAN = "clean"


class EnduranceMode(str, Enum):
    """Endurance activity modes."""
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"


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
    
    # Capacity update
    g_l: float = 0.015  # Fitness contribution to capacity
    h_l: float = 0.010  # Fatigue reduction of capacity
    lambda_l: float = 0.0  # Detraining (v1: none)
    C_min: float = 20.0  # Minimum capacity floor
    
    # Interference coefficients
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


@dataclass
class StrengthImpulses:
    """Aggregated impulses from all strength sets on a day."""
    per_lift: Dict[str, float]  # u_l per lift
    u_sys: float  # System impulse
    u_legs: float  # Legs aggregate
    u_met: float  # Metabolic strength impulse
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
    """Full day state for an athlete."""
    date: date
    per_lift: Dict[str, PerLiftState] = field(default_factory=dict)
    D_sys: float = 0.0  # System fatigue (0-1+)
    R_mito: float = 0.0  # Recovery capacity (0+)
    E_fat: float = 0.0  # Endurance fatigue (0-1+)
    
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
        
        # Metabolic impulse (simple: all high-rep sets count)
        if s.reps >= 8:
            u_met += s.tonnage * (1.0 + 0.5 * s.vl)
    
    return StrengthImpulses(
        per_lift=per_lift,
        u_sys=u_sys,
        u_legs=u_legs,
        u_met=u_met,
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
    Compute interference from endurance to strength.
    
    Returns:
        Tuple of (per_lift_interference, system_interference)
    """
    if not endurance.has_HIIT or endurance.u_E_HIIT <= 0:
        return ({lift: 0.0 for lift in params.omega.keys()}, 0.0)
    
    mode_factor = params.get_mode_factor(endurance.mode)
    base_interf = endurance.u_E_HIIT * mode_factor * timing_factor
    
    # Per-lift interference
    per_lift = {}
    for lift in params.omega.keys():
        k_ES = params.get_k_ES(lift)
        per_lift[lift] = k_ES * base_interf
    
    # System interference
    sys_interf = params.k_ES_sys * base_interf
    
    return (per_lift, sys_interf)


def update_day_state(
    current: DayState,
    impulses: DailyImpulses,
    params: DayEngineParams,
    has_priming: bool = False
) -> DayState:
    """
    Update day state from day d to d+1 using impulses.
    
    Args:
        current: Current day state
        impulses: Daily impulses
        params: Engine parameters
        has_priming: Whether Z2 priming is active
    
    Returns:
        Updated DayState
    """
    R = current.R_mito
    
    # Recovery capacity update
    new_R_mito = R * math.exp(-1.0 / params.tau_mito) + params.k_mito * impulses.endurance.u_E_Z2
    
    # Compute interference
    interf_per_lift, interf_sys = compute_interference(impulses.endurance, params)
    
    # Create new state
    new_state = DayState(
        date=current.date + timedelta(days=1),
        per_lift={},
        D_sys=0.0,  # Will compute below
        R_mito=new_R_mito,
        E_fat=0.0   # Will compute below
    )
    
    # Per-lift updates
    for lift in list(current.per_lift.keys()) + list(impulses.strength.per_lift.keys()):
        current_lift = current.get_lift(lift)
        
        # Fatigue update
        tau_eff = params.get_tau_Dl(lift) / (1.0 + params.get_beta_l(lift) * R)
        D_new = current_lift.D_l * math.exp(-1.0 / tau_eff)
        D_new += params.k_Dl * impulses.strength.per_lift.get(lift, 0.0)
        D_new += interf_per_lift.get(lift, 0.0)
        
        # Fitness update with optional priming
        F_new = current_lift.F_l * math.exp(-1.0 / params.tau_Fl)
        priming = 1.0 + params.priming_gain if has_priming else 1.0
        F_new += params.k_Fl * impulses.strength.per_lift.get(lift, 0.0) * priming
        
        # Capacity update
        C_new = max(
            params.C_min,
            current_lift.C_l + params.g_l * F_new - params.h_l * D_new - params.lambda_l
        )
        
        new_state.per_lift[lift] = PerLiftState(
            D_l=max(0.0, D_new),
            F_l=max(0.0, F_new),
            C_l=C_new
        )
    
    # System fatigue update
    tau_sys_eff = params.tau_sys / (1.0 + params.beta_sys * R)
    D_sys_new = current.D_sys * math.exp(-1.0 / tau_sys_eff)
    D_sys_new += params.k_sys * impulses.strength.u_sys
    D_sys_new += interf_sys
    new_state.D_sys = max(0.0, D_sys_new)
    
    # Endurance fatigue update
    E_fat_new = current.E_fat * math.exp(-1.0 / params.tau_Efat)
    E_fat_new += params.k_EHIIT * impulses.endurance.u_E_HIIT
    E_fat_new += params.k_SE * impulses.strength.u_legs
    new_state.E_fat = max(0.0, E_fat_new)
    
    return new_state


def compute_readiness(
    state: DayState,
    params: DayEngineParams
) -> ReadinessOutput:
    """
    Compute readiness scores from current state.
    
    Args:
        state: Current day state
        params: Engine parameters
    
    Returns:
        ReadinessOutput with scores and explanations
    """
    per_lift = {}
    explanations = []
    
    # Per-lift readiness
    for lift, lift_state in state.per_lift.items():
        # Readiness = 1 - D_l - w_sys * D_sys
        readiness = 1.0 - lift_state.D_l - params.w_sys * state.D_sys
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
    
    if state.R_mito > 0.3:
        explanations.append("Recovery capacity elevated from recent Z2 work")
    
    if state.E_fat > 0.3:
        explanations.append("Endurance fatigue elevated - monitor HIIT volume")
    
    # Per-lift explanations
    for lift, lift_state in state.per_lift.items():
        if lift_state.D_l > 0.4:
            explanations.append(f"{lift}: local fatigue elevated")
        if lift_state.C_l > 110:  # Improved capacity
            explanations.append(f"{lift}: capacity trending up")
    
    if not explanations:
        explanations.append("Readiness neutral - train as planned")
    
    return ReadinessOutput(
        per_lift=per_lift,
        endurance=endurance_ready,
        overall=overall,
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
    Main entry point: simulate one day transition.
    
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
        E_fat=0.0
    )
