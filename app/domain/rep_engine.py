"""
Rep-level fatigue estimator (VBT-driven) for concurrent strength training.

SPRINT H1: MODEL HARDENING & IDENTIFIABILITY
- Replaced dimensionless M with x_M = ln(A_M) log-space metabolic availability
- Fixed fatigue driver: y_phi = min(y, 1.0) prevents anti-fatigue when y>1
- Added catastrophe nonlinearity for high velocity loss (VL > 0.40)
- Added central driver density factor (reps per minute / rest) for identifiability
- Added optional set_end_rpe for central vs local fatigue split
- Hardened velocity prediction using x_M instead of exp(-kM*M)

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
    delta: float = 1.0  # Exponent on (1/y_phi) in phi calculation
    eta_M: float = 0.15  # Metabolic penalty on local fatigue
    eta_Mrest: float = 0.02  # Metabolic penalty on recovery
    a_M: float = 0.015  # Metabolic increment per rep
    
    # H1: Removed kM (no longer used with x_M log-space)
    # kM: float = 0.6  # DEPRECATED: Metabolic velocity damping factor
    
    # H1: Catastrophe nonlinearity parameters
    vl_catastrophe_threshold: float = 0.40  # VL threshold for catastrophe
    catastrophe_exponent: float = 2.0  # Power for catastrophe term
    
    # H1: Central fatigue density factor
    enable_density_factor: bool = True  # Enable central fatigue density factor
    density_alpha: float = 1.5  # Exponent for density factor
    
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
    # H1: Optional RPE at end of set for central vs local split
    set_end_rpe: Optional[float] = None  # 1-10 scale, None if not available


@dataclass
class SessionInput:
    """Input data for a full strength session."""
    sets: List[SetInput]
    profiles: Dict[str, LiftVelocityProfile]  # Per-lift velocity profiles
    init_A_local: Dict[str, float]  # Initial A_l per lift (from day state)
    init_A_sys: float  # Initial system availability
    init_M: float  # Initial metabolic state (legacy, converted to x_M)
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
    y_phi: float  # H1: Clamped fatigue driver (min(y, 1.0))
    A_l: float  # Local availability
    A_sys: float  # System availability
    A_M: float  # H1: Metabolic availability (replaces M)
    v_pred_next: float  # Predicted velocity for next rep
    limiting: str  # Primary limiting factor
    phi: float  # H1: Fatigue impulse for transparency


@dataclass
class SetOutput:
    """Output data for a set."""
    lift: str
    load_kg: float
    VL: float  # Velocity loss percentage
    VL_catastrophe: float  # H1: Catastrophe factor applied
    density_factor: float  # H1: Central fatigue density factor
    reps: List[RepOutput]


@dataclass
class SessionOutput:
    """Output data for full session."""
    sets: List[SetOutput]
    final_A_local: Dict[str, float]
    final_A_sys: float
    final_A_M: float  # H1: Final metabolic availability (replaces final_M)
    # H1: Legacy M values for backward compatibility
    final_M: float = 0.0


class RepState:
    """
    Internal mutable state tracker for a session.
    
    Uses log-availability representation (x_l, x_sys, x_M) for numerical stability.
    """
    
    def __init__(
        self,
        A_local_init: Dict[str, float],
        A_sys_init: float,
        M_init: float,  # Legacy, converted to x_M
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
        
        # H1: Convert legacy M to x_M log-space
        # A_M = exp(-kM * M) from old model, so x_M = -kM * M
        # For new model, we directly track x_M = ln(A_M)
        kM_legacy = 0.6  # Legacy conversion factor
        A_M_init = math.exp(-kM_legacy * max(0.0, M_init))
        self.x_M = math.log(max(params.min_A, min(1.0, A_M_init)))
        
        # H1: Track set-level data for density factor
        self.prev_set_end_time: Optional[float] = None
        self.current_set_rep_count: int = 0
    
    @property
    def A_sys(self) -> float:
        """Current system availability."""
        return math.exp(self.x_sys)
    
    def A_local(self, lift: str) -> float:
        """Current local availability for a lift."""
        return math.exp(self.x_local.get(lift, self.min_log))
    
    @property
    def A_M(self) -> float:
        """H1: Current metabolic availability."""
        return math.exp(self.x_M)
    
    # H1: Legacy M property for backward compatibility
    @property
    def M(self) -> float:
        """Legacy metabolic state (approximated from A_M)."""
        kM_legacy = 0.6
        return max(0.0, -math.log(self.A_M) / kM_legacy) if self.A_M > 0 else 0.0
    
    def _get_lift_params(self, lift: str) -> Tuple[float, float, float]:
        """Get (a_local, a_sys, tau_rest_local) for lift."""
        return self.params.get_lift_params(lift)
    
    def compute_phi(
        self,
        load_kg: float,
        y: float,
        e1rm: Optional[float] = None,
        vl_catastrophe: float = 0.0,
        density_factor: float = 1.0
    ) -> Tuple[float, float]:
        """
        H1: Compute rep-load factor phi with hardened fatigue driver.
        
        phi = (I^alpha) * ((1/y_phi)^delta) * catastrophe_mult * density_mult
        
        where:
        - y_phi = min(y, 1.0)  [prevents anti-fatigue when y>1]
        - I = load/e1rm if available, else 1.0
        - catastrophe_mult = (1 + (VL / vl_threshold)^exponent) if VL > threshold
        - density_mult = density_factor^density_alpha for central fatigue
        
        Returns: (phi_local, phi_central)
        """
        # H1: Clamped fatigue driver - y>1 does NOT reduce fatigue
        y_phi = min(y, 1.0)
        
        # Intensity proxy
        if e1rm and e1rm > 0:
            I = load_kg / e1rm
        else:
            I = 1.0  # Fallback when e1rm unknown
        
        # Base phi calculation
        phi_base = (I ** self.params.alpha) * ((1.0 / max(y_phi, self.params.min_y)) ** self.params.delta)
        
        # H1: Catastrophe nonlinearity for high velocity loss
        catastrophe_mult = 1.0
        if vl_catastrophe > self.params.vl_catastrophe_threshold:
            excess_vl = (vl_catastrophe - self.params.vl_catastrophe_threshold) / (1.0 - self.params.vl_catastrophe_threshold)
            catastrophe_mult = 1.0 + (excess_vl ** self.params.catastrophe_exponent)
        
        # H1: Density factor affects central more than local
        density_mult = 1.0
        if self.params.enable_density_factor:
            density_mult = density_factor ** self.params.density_alpha
        
        phi_local = phi_base * catastrophe_mult
        phi_central = phi_base * catastrophe_mult * density_mult
        
        return phi_local, phi_central, y_phi
    
    def compute_chi(self, rep_index: int) -> float:
        """
        Compute metabolic increment chi.
        Simple model: 1.0 + small scaling with rep index.
        """
        return 1.0 + 0.05 * rep_index
    
    def compute_density_factor(
        self,
        rest_sec: Optional[float],
        reps_in_set: int
    ) -> float:
        """
        H1: Compute central fatigue density factor.
        
        Higher density (short rest, many reps) = higher central fatigue.
        
        density_factor = (reps_per_minute)^0.5 = (reps / (rest_min + 1))^0.5
        
        Args:
            rest_sec: Rest time before this set (None for first set)
            reps_in_set: Number of reps in the set
        
        Returns:
            Density factor (1.0 = baseline)
        """
        if not self.params.enable_density_factor:
            return 1.0
        
        if rest_sec is None or rest_sec <= 0:
            # First set or no rest - use moderate baseline
            return 1.0
        
        # Convert to minutes and add 1 to avoid division by zero
        rest_min = rest_sec / 60.0
        reps_per_minute = reps_in_set / (rest_min + 0.5)  # +0.5 for continuous smoothing
        
        # Scale: 10 reps/min => ~1.4, 5 reps/min => 1.0, 2 reps/min => ~0.6
        density_factor = math.sqrt(reps_per_minute / 5.0)
        
        # Clamp to reasonable range
        return max(0.5, min(2.0, density_factor))
    
    def apply_rep(
        self,
        lift: str,
        load_kg: float,
        y: float,
        rep_index: int,
        e1rm: Optional[float] = None,
        vl_catastrophe: float = 0.0,
        density_factor: float = 1.0,
        set_end_rpe: Optional[float] = None
    ) -> Tuple[float, float, float, float, float, str]:
        """
        H1: Apply fatigue from one rep with hardened model.
        
        Returns: (A_l, A_sys, A_M, v_pred_next, y_phi, limiting_factor)
        """
        a_local, a_sys, _ = self._get_lift_params(lift)
        
        # H1: Compute phi with catastrophe and density
        phi_local, phi_central, y_phi = self.compute_phi(
            load_kg, y, e1rm, vl_catastrophe, density_factor
        )
        chi = self.compute_chi(rep_index)
        
        # H1: Optional RPE-based split between central and local
        if set_end_rpe is not None:
            # Higher RPE (>8) suggests more central/systemic fatigue
            rpe_factor = max(0.0, (set_end_rpe - 7.0) / 3.0)  # 0 to 1
            # Blend local and central based on RPE
            phi_local = phi_local * (1.0 - 0.3 * rpe_factor)
            phi_central = phi_central * (1.0 + 0.3 * rpe_factor)
        
        # Update local log-availability
        A_M = self.A_M
        delta_x_local = a_local * phi_local * (1.0 + self.params.eta_M * (1.0 - A_M))
        self.x_local[lift] = max(self.min_log, self.x_local.get(lift, self.min_log) - delta_x_local)
        
        # Update system log-availability (uses central phi with density factor)
        delta_x_sys = a_sys * phi_central
        self.x_sys = max(self.min_log, self.x_sys - delta_x_sys)
        
        # H1: Update metabolic log-availability (x_M instead of M)
        # A_M decreases (x_M becomes more negative) with metabolic stress
        delta_x_M = -self.params.a_M * chi
        self.x_M = max(self.min_log, self.x_M + delta_x_M)
        
        # Compute outputs
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        
        return A_l, A_sys, A_M, y_phi, phi_local
    
    def apply_rest(self, delta_t: float, R_mito: float = 0.0) -> None:
        """
        H1: Apply recovery during rest period with hardened model.
        
        Args:
            delta_t: Rest duration in seconds
            R_mito: Recovery capacity factor (0-1+)
        """
        if delta_t <= 0:
            return
        
        R = max(0.0, min(1.0, R_mito))  # H1: Bound R_mito to [0, 1]
        
        # Recovery magnitude boost from R_mito
        recovery_boost = 1.0 + self.params.beta_rest * R
        
        # Update each lift's local availability
        for lift in self.x_local:
            _, _, tau_rest_local = self._get_lift_params(lift)
            a_local, _, _ = self._get_lift_params(lift)
            r_local = a_local * 1.2  # r_local proportional to a_local
            
            recovery = r_local * (1.0 - math.exp(-delta_t / tau_rest_local)) * recovery_boost
            # H1: Metabolic penalty uses (1 - A_M) instead of M
            A_M = self.A_M
            self.x_local[lift] = min(0.0, self.x_local[lift] + recovery - self.params.eta_Mrest * (1.0 - A_M))
            self.x_local[lift] = max(self.min_log, self.x_local[lift])
        
        # Update system availability
        recovery_sys = self.params.r_sys * (1.0 - math.exp(-delta_t / self.params.tau_rest_sys)) * recovery_boost
        A_M = self.A_M
        self.x_sys = min(0.0, self.x_sys + recovery_sys - self.params.eta_Mrest * (1.0 - A_M))
        self.x_sys = max(self.min_log, self.x_sys)
        
        # H1: Update metabolic recovery using x_M log-space
        # A_M recovers toward 1.0 (x_M toward 0)
        tau_M_eff = self.params.tau_M / (1.0 + self.params.beta_M * R)
        recovery_M = (1.0 - math.exp(-delta_t / tau_M_eff))
        # Move x_M toward 0 (A_M toward 1)
        self.x_M = min(0.0, self.x_M + recovery_M * (-self.x_M))
        self.x_M = max(self.min_log, self.x_M)
    
    def predict_velocity(self, v_ref: float, lift: str) -> float:
        """
        H1: Predict velocity using hardened model.
        
        Uses x_M log-space: v_pred = v_ref * A_l * A_sys * A_M
        (A_M = exp(x_M) directly, no exp(-kM*M) needed)
        """
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        A_M = self.A_M
        return v_ref * A_l * A_sys * A_M
    
    def get_limiting_factor(self, lift: str) -> LimitingFactor:
        """
        H1: Determine primary limiting factor with hardened model.
        
        Compares local availability, system availability, and metabolic availability.
        """
        A_l = self.A_local(lift)
        A_sys = self.A_sys
        A_M = self.A_M
        
        # Find minimum (most limiting)
        if A_sys < A_l and A_sys < A_M:
            return LimitingFactor.CENTRAL
        elif A_l < A_sys and A_l < A_M:
            return LimitingFactor.LOCAL
        else:
            return LimitingFactor.METABOLIC


def simulate_strength_session(session_input: SessionInput) -> SessionOutput:
    """
    H1: Simulate a full strength session with hardened rep-level fatigue tracking.
    
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
        
        # H1: Compute density factor for this set
        density_factor = state.compute_density_factor(
            set_input.rest_before_sec,
            len(set_input.velocities)
        )
        
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
        
        # Track velocity for catastrophe calculation
        v_first = set_input.velocities[0] if set_input.velocities else 0.0
        
        for rep_idx, v_obs in enumerate(set_input.velocities):
            # Compute reference velocity
            v_ref = profile.v_ref(load_kg)
            
            # Normalize observation
            y = max(params.min_y, min(params.max_y, v_obs / v_ref))
            
            # H1: Compute velocity loss for catastrophe
            vl_current = 1.0 - (v_obs / v_first) if v_first > 0 and rep_idx > 0 else 0.0
            
            # H1: Apply rep fatigue with hardened model
            A_l, A_sys, A_M, y_phi, phi = state.apply_rep(
                lift=lift,
                load_kg=load_kg,
                y=y,
                rep_index=rep_idx,
                e1rm=e1rm,
                vl_catastrophe=vl_current,
                density_factor=density_factor,
                set_end_rpe=set_input.set_end_rpe
            )
            
            # Predict next velocity
            v_pred_next = state.predict_velocity(v_ref, lift)
            
            # Get limiting factor
            limiting = state.get_limiting_factor(lift).value
            
            rep_outputs.append(RepOutput(
                v_ref=v_ref,
                y=y,
                y_phi=y_phi,  # H1: Include clamped driver
                A_l=A_l,
                A_sys=A_sys,
                A_M=A_M,  # H1: Metabolic availability
                v_pred_next=v_pred_next,
                limiting=limiting,
                phi=phi  # H1: Include phi for transparency
            ))
        
        # Compute set summary
        if len(rep_outputs) >= 2:
            v_first = set_input.velocities[0]
            v_last = set_input.velocities[-1]
            VL = 1.0 - (v_last / v_first) if v_first > 0 else 0.0
        else:
            VL = 0.0
        
        # H1: Compute final catastrophe factor for set
        vl_catastrophe = VL
        
        set_outputs.append(SetOutput(
            lift=lift,
            load_kg=load_kg,
            VL=VL,
            VL_catastrophe=vl_catastrophe,  # H1: Include catastrophe
            density_factor=density_factor,  # H1: Include density factor
            reps=rep_outputs
        ))
    
    # Build final output
    final_A_local = {lift: state.A_local(lift) for lift in state.x_local}
    
    return SessionOutput(
        sets=set_outputs,
        final_A_local=final_A_local,
        final_A_sys=state.A_sys,
        final_A_M=state.A_M,  # H1: New metabolic availability
        final_M=state.M  # H1: Legacy M for backward compatibility
    )
