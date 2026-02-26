"""
Rep-level fatigue estimator (VBT-driven) for concurrent strength training.

This module provides deterministic, testable domain logic for tracking fatigue
across reps and sets using velocity-based training (VBT) data.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
from enum import Enum


class LimitingFactor(str, Enum):
    """Classification of the primary limiting factor."""
    LOCAL = "local"
    CENTRAL = "central"
    METABOLIC = "metabolic"


@dataclass(frozen=True)
class LiftVelocityProfile:
    """
    Load-velocity profile for a lift: v_ref(w) = a - b*w, clamped to v_min.
    
    Args:
        lift: Lift identifier (e.g., 'squat', 'bench')
        a: Velocity intercept (m/s at load=0)
        b: Slope (m/s per kg)
        v_min: Minimum velocity floor (default 0.05 m/s)
    """
    lift: str
    a: float
    b: float
    v_min: float = 0.05
    
    def v_ref(self, load_kg: float) -> float:
        """Reference velocity at given load when fresh."""
        return max(self.v_min, self.a - self.b * load_kg)


@dataclass(frozen=True)
class RepEngineParams:
    """
    Configurable parameters for the rep-level fatigue engine.
    
    All values have sensible defaults based on literature and practice.
    """
    # Update coefficients
    alpha: float = 1.3  # Exponent on intensity in phi calculation
    delta: float = 1.0  # Exponent on (1/y) in phi calculation
    eta_M: float = 0.15  # Metabolic penalty on local fatigue
    eta_Mrest: float = 0.02  # Metabolic penalty on recovery
    a_M: float = 0.015  # Metabolic increment per rep
    kM: float = 0.6  # Metabolic velocity damping factor
    
    # Recovery parameters
    tau_rest_sys: float = 120.0  # System recovery time constant (s)
    tau_M: float = 180.0  # Metabolic clearance time constant (s)
    beta_M: float = 0.5  # R_mito effect on metabolic clearance
    beta_rest: float = 0.25  # R_mito effect on recovery rate
    r_sys: float = 0.25  # System recovery magnitude
    
    # Per-lift parameters (defaults by lift type)
    # Format: {lift: (a_local, a_sys, tau_rest_local)}
    lift_params: Dict[str, Tuple[float, float, float]] = field(default_factory=lambda: {
        'squat': (0.018, 0.026, 90.0),
        'deadlift': (0.020, 0.030, 90.0),
        'power_clean': (0.016, 0.024, 90.0),
        'bench': (0.014, 0.016, 60.0),
        'press': (0.014, 0.016, 60.0),
    })
    
    # State clamping
    min_A: float = 0.02  # Minimum availability (clamping floor)
    max_y: float = 1.5   # Maximum observational normalization
    min_y: float = 0.05  # Minimum observational normalization
    
    def get_lift_params(self, lift: str) -> Tuple[float, float, float]:
        """
        Get (a_local, a_sys, tau_rest_local) for a lift.
        Returns bench defaults if lift not found.
        """
        return self.lift_params.get(lift, (0.014, 0.016, 60.0))


@dataclass
class RepInput:
    """Input data for a single rep."""
    lift: str
    load_kg: float
    v_obs: float  # Observed velocity (m/s)
    rep_index: int  # 0-based within set
    set_index: int  # 0-based within session


@dataclass
class SetInput:
    """Input data for a set (collection of reps)."""
    lift: str
    load_kg: float
    velocities: List[float]  # Observed velocities per rep
    rest_before_sec: Optional[float] = None  # Rest before this set


@dataclass
class SessionInput:
    """Input data for a full strength session."""
    sets: List[SetInput]
    profiles: Dict[str, LiftVelocityProfile]  # Per-lift velocity profiles
    init_A_local: Dict[str, float]  # Initial A_l per lift (from day state)
    init_A_sys: float  # Initial system availability
    init_M: float  # Initial metabolic state
    R_mito: float  # Recovery capacity (0-1+)
    e1rm: Optional[Dict[str, float]] = None  # Estimated 1RM per lift (optional)
    athlete_id: Optional[str] = None
    date: Optional[str] = None
    params: Optional[RepEngineParams] = None  # Override default params


@dataclass
class RepOutput:
    """Output data for a single rep."""
    v_ref: float  # Reference velocity
    y: float  # Normalized freshness signal
    A_l: float  # Local availability
    A_sys: float  # System availability
    M: float  # Metabolic limiter
    v_pred_next: float  # Predicted velocity for next rep
    limiting: str  # Primary limiting factor


@dataclass
class SetOutput:
    """Output data for a set."""
    lift: str
    load_kg: float
    VL: float  # Velocity loss percentage
    reps: List[RepOutput]


@dataclass
class SessionOutput:
    """Output data for full session."""
    sets: List[SetOutput]
    final_A_local: Dict[str, float]
    final_A_sys: float
    final_M: float


class RepState:
    """
    Internal mutable state tracker for a session.
    
    Uses log-availability representation (x_l, x_sys) for numerical stability.
    """
    
    def __init__(
        self,
        A_local_init: Dict[str, float],
        A_sys_init: float,
        M_init: float,
        params: RepEngineParams
    ):
        self.params = params
        self.min_log = math.log(params.min_A)  # ln(0.02) ~= -3.91
        
        # Initialize log-availability states
        self.x_local: Dict[str, float] = {
            lift: math.log(max(params.min_A, min(1.0, A)))
            for lift, A in A_local_init.items()
        }
        self.x_sys = math.log(max(params.min_A, min(1.0, A_sys_init)))
        self.M = max(0.0, M_init)
    
    @property
    def A_sys(self) -> float:
        """Current system availability."""
        return math.exp(self.x_sys)
    
    def A_local(self, lift: str) -> float:
        """Current local availability for a lift."""
        return math.exp(self.x_local.get(lift, self.min_log))
    
    def _get_lift_params(self, lift: str) -> Tuple[float, float, float]:
        """Get (a_local, a_sys, tau_rest_local) for lift."""
        return self.params.get_lift_params(lift)
    
    def compute_phi(self, load_kg: float, y: float, e1rm: Optional[float] = None) -> float:
        """
        Compute rep-load factor phi.
        
        phi = (I^alpha) * ((1/y)^delta)
        where I = load/e1rm if available, else 1.0
        """
        # Intensity proxy
        if e1rm and e1rm > 0:
            I = load_kg / e1rm
        else:
            I = 1.0  # Fallback when e1rm unknown
        
        # Clamp y to avoid division by zero
        y_clamped = max(self.params.min_y, min(self.params.max_y, y))
        
        phi = (I ** self.params.alpha) * ((1.0 / y_clamped) ** self.params.delta)
        return phi
    
    def compute_chi(self, rep_index: int) -> float:
        """
        Compute metabolic increment chi.
        Simple model: 1.0 + small scaling with rep index.
        """
        return 1.0 + 0.05 * rep_index
    
    def apply_rep(
        self,
        lift: str,
        load_kg: float,
        y: float,
        rep_index: int,
        e1rm: Optional[float] = None
    ) -> Tuple[float, float, float, float, str]:
        """
        Apply fatigue from one rep.
        
        Returns: (A_l, A_sys, M, v_pred_next, limiting_factor)
        """
        a_local, a_sys, _ = self._get_lift_params(lift)
        
        # Compute phi
        phi = self.compute_phi(load_kg, y, e1rm)
        chi = self.compute_chi(rep_index)
        
        # Update local log-availability
        delta_x_local = a_local * phi * (1.0 + self.params.eta_M * self.M)
        self.x_local[lift] = max(self.min_log, self.x_local.get(lift, self.min_log) - delta_x_local)
        
        # Update system log-availability
        delta_x_sys = a_sys * phi
        self.x_sys = max(self.min_log, self.x_sys - delta_x_sys)
        
        # Update metabolic state
        self.M += self.params.a_M * chi
        
        # Compute outputs
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        M = self.M
        
        return A_l, A_sys, M
    
    def apply_rest(self, delta_t: float, R_mito: float = 0.0) -> None:
        """
        Apply recovery during rest period.
        
        Args:
            delta_t: Rest duration in seconds
            R_mito: Recovery capacity factor (0-1+)
        """
        if delta_t <= 0:
            return
        
        R = R_mito  # Recovery capacity factor
        
        # Recovery magnitude boost from R_mito
        recovery_boost = 1.0 + self.params.beta_rest * R
        
        # Update each lift's local availability
        for lift in self.x_local:
            _, _, tau_rest_local = self._get_lift_params(lift)
            a_local, _, _ = self._get_lift_params(lift)
            r_local = a_local * 1.2  # r_local proportional to a_local
            
            recovery = r_local * (1.0 - math.exp(-delta_t / tau_rest_local)) * recovery_boost
            self.x_local[lift] = min(0.0, self.x_local[lift] + recovery - self.params.eta_Mrest * self.M)
            self.x_local[lift] = max(self.min_log, self.x_local[lift])
        
        # Update system availability
        recovery_sys = self.params.r_sys * (1.0 - math.exp(-delta_t / self.params.tau_rest_sys)) * recovery_boost
        self.x_sys = min(0.0, self.x_sys + recovery_sys - self.params.eta_Mrest * self.M)
        self.x_sys = max(self.min_log, self.x_sys)
        
        # Update metabolic clearance
        tau_M_eff = self.params.tau_M / (1.0 + self.params.beta_M * R)
        self.M *= math.exp(-delta_t / tau_M_eff)
    
    def predict_velocity(self, v_ref: float, lift: str) -> float:
        """Predict velocity for next rep given reference."""
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        M = self.M
        return v_ref * A_l * A_sys * math.exp(-self.params.kM * M)
    
    def get_limiting_factor(self, lift: str) -> LimitingFactor:
        """
        Determine primary limiting factor.
        
        Compares local availability, system availability, and metabolic damping.
        """
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        metabolic_factor = math.exp(-self.params.kM * self.M)
        
        # Find minimum (most limiting)
        if A_sys < A_l and A_sys < metabolic_factor:
            return LimitingFactor.CENTRAL
        elif A_l < A_sys and A_l < metabolic_factor:
            return LimitingFactor.LOCAL
        else:
            return LimitingFactor.METABOLIC


def simulate_strength_session(session_input: SessionInput) -> SessionOutput:
    """
    Simulate a full strength session with rep-level fatigue tracking.
    
    This is the main entry point for the rep-level engine.
    """
    params = session_input.params or RepEngineParams()
    
    # Initialize state
    state = RepState(
        A_local_init=session_input.init_A_local,
        A_sys_init=session_input.init_A_sys,
        M_init=session_input.init_M,
        params=params
    )
    
    set_outputs: List[SetOutput] = []
    
    for set_idx, set_input in enumerate(session_input.sets):
        lift = set_input.lift
        load_kg = set_input.load_kg
        
        # Apply rest before this set (if not first set)
        if set_input.rest_before_sec is not None and set_input.rest_before_sec > 0:
            state.apply_rest(set_input.rest_before_sec, R_mito=session_input.R_mito)
        
        # Get profile and e1rm for this lift
        profile = session_input.profiles.get(lift)
        if not profile:
            # Create default profile if not provided
            profile = LiftVelocityProfile(lift=lift, a=0.5, b=0.003)
        
        e1rm = None
        if session_input.e1rm and lift in session_input.e1rm:
            e1rm = session_input.e1rm[lift]
        
        # Process reps
        rep_outputs: List[RepOutput] = []
        
        for rep_idx, v_obs in enumerate(set_input.velocities):
            # Compute reference velocity
            v_ref = profile.v_ref(load_kg)
            
            # Normalize observation
            y = max(params.min_y, min(params.max_y, v_obs / v_ref))
            
            # Apply rep fatigue
            A_l, A_sys, M = state.apply_rep(
                lift=lift,
                load_kg=load_kg,
                y=y,
                rep_index=rep_idx,
                e1rm=e1rm
            )
            
            # Predict next velocity
            v_pred_next = state.predict_velocity(v_ref, lift)
            
            # Get limiting factor
            limiting = state.get_limiting_factor(lift).value
            
            rep_outputs.append(RepOutput(
                v_ref=v_ref,
                y=y,
                A_l=A_l,
                A_sys=A_sys,
                M=M,
                v_pred_next=v_pred_next,
                limiting=limiting
            ))
        
        # Compute set summary
        if len(rep_outputs) >= 2:
            v_first = set_input.velocities[0]
            v_last = set_input.velocities[-1]
            VL = 1.0 - (v_last / v_first) if v_first > 0 else 0.0
        else:
            VL = 0.0
        
        set_outputs.append(SetOutput(
            lift=lift,
            load_kg=load_kg,
            VL=VL,
            reps=rep_outputs
        ))
    
    # Build final output
    final_A_local = {lift: state.A_local(lift) for lift in state.x_local}
    
    return SessionOutput(
        sets=set_outputs,
        final_A_local=final_A_local,
        final_A_sys=state.A_sys,
        final_M=state.M
    )
