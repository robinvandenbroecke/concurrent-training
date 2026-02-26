"""
Concurrent Training Domain Model

Implements the mathematical model for fatigue, fitness, and autoregulation
in concurrent strength and endurance training.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from app.types import LiftType, EnduranceSport, EnduranceIntensity


@dataclass
class LiftProfile:
    """Load-velocity profile: v = a - b*w"""
    lift: LiftType
    a: float  # velocity intercept (m/s)
    b: float  # slope (m/s/kg)
    
    def v_ref(self, weight: float) -> float:
        """Reference velocity for given weight"""
        return max(0.1, self.a - self.b * weight)
    
    def estimate_1rm(self, weight: float, velocity: float) -> float:
        """Estimate 1RM from a rep"""
        if velocity >= self.a:
            return weight * 1.1  # Conservative estimate
        return weight + (self.a - velocity) / self.b


@dataclass 
class RepLevelState:
    """Rep-level fatigue states (updated each rep)"""
    x_l: float = 0.0  # ln(A_l), local availability
    x_sys: float = 0.0  # ln(A_sys), system availability
    M: float = 0.0  # metabolic limitation
    
    @property
    def A_l(self) -> float:
        return math.exp(self.x_l)
    
    @property
    def A_sys(self) -> float:
        return math.exp(self.x_sys)
    
    def predict_velocity(self, v_ref: float, kM: float = 0.5) -> float:
        """Predict velocity given reference and current state"""
        return v_ref * self.A_l * self.A_sys * math.exp(-kM * self.M)


@dataclass
class DayLevelState:
    """Day-level states (updated daily)"""
    date: str
    
    # Per-lift states
    D_l: Dict[LiftType, float] = field(default_factory=dict)  # Fatigue
    F_l: Dict[LiftType, float] = field(default_factory=dict)  # Fitness/adaptation
    C_l: Dict[LiftType, float] = field(default_factory=dict)  # Capacity (e1RM-like)
    
    # System states
    D_sys: float = 0.0  # System fatigue
    R_mito: float = 0.0  # Recovery capacity (improved by Z2)
    E_fat: float = 0.0  # Endurance fatigue
    
    def __post_init__(self):
        # Initialize lifts if not set
        for lift in LiftType:
            if lift not in self.D_l:
                self.D_l[lift] = 0.0
            if lift not in self.F_l:
                self.F_l[lift] = 1.0
            if lift not in self.C_l:
                self.C_l[lift] = 100.0  # Default capacity


@dataclass
class SystemParameters:
    """Configurable parameters for the model"""
    # Rep-level parameters
    alpha_l: float = 0.05  # Local fatigue accumulation rate
    alpha_sys: float = 0.03  # System fatigue accumulation rate
    alpha_M: float = 0.08  # Metabolic accumulation rate
    etaM: float = 0.3  # Metabolic amplification of local fatigue
    kM: float = 0.5  # Metabolic impact on velocity
    
    # Recovery parameters
    r_l: float = 0.1  # Local recovery rate
    r_sys: float = 0.08  # System recovery rate
    tau_rest_l: float = 180.0  # Local rest time constant (s)
    tau_rest_sys: float = 240.0  # System rest time constant (s)
    tau_M: float = 300.0  # Metabolic clearance time constant (s)
    beta_rest: float = 0.2  # R_mito boost to recovery
    etaMrest: float = 0.1  # Metabolic impact on recovery
    beta_M: float = 0.15  # R_mito boost to metabolic clearance
    
    # Day-level parameters
    tau_Dl: float = 3.0  # Days - per-lift fatigue decay
    tau_Sys: float = 4.0  # Days - system fatigue decay
    tau_mito: float = 7.0  # Days - R_mito decay
    tau_Efat: float = 2.0  # Days - endurance fatigue decay
    
    k_Dl: float = 0.001  # Per-lift fatigue accumulation
    k_Sys: float = 0.0008  # System fatigue accumulation
    k_mito: float = 0.05  # R_mito buildup from Z2
    k_EHIIT: float = 0.08  # Endurance fatigue from HIIT
    k_SE: float = 0.0005  # Strength-to-endurance fatigue (legs)
    
    # Interference parameters
    k_ES_squat: float = 0.002  # HIIT to squat interference
    k_ES_deadlift: float = 0.0015  # HIIT to deadlift interference
    k_ES_bench: float = 0.0005  # HIIT to bench interference
    k_ES_press: float = 0.0005  # HIIT to press interference
    k_ES_clean: float = 0.001  # HIIT to clean interference
    
    beta_l: float = 0.3  # R_mito reduces fatigue decay time
    beta_sys: float = 0.25  # R_mito reduces system fatigue decay time
    
    # Metabolic base from endurance
    theta: float = 0.02  # Endurance contribution to M_base
    zeta: float = 0.01  # Strength metabolic contribution to M_base
    
    # Autoregulation thresholds
    vl_max_default: float = 20.0  # % velocity loss
    v_floor_pct: float = 0.3  # Minimum velocity as % of v_ref


class ConcurrentTrainingModel:
    """Core domain model implementing all equations"""
    
    def __init__(self, params: Optional[SystemParameters] = None):
        self.params = params or SystemParameters()
    
    def compute_phi(self, intensity: float, v_ratio: float) -> float:
        """
        Compute fatigue drive phi from intensity and velocity deficit
        intensity: 0-1 (load/1RM)
        v_ratio: v_ref/v_obs (how much slower than expected)
        """
        base_phi = intensity ** 1.5
        velocity_factor = max(1.0, v_ratio ** 0.5)
        return base_phi * velocity_factor
    
    def compute_chi(self, rep_num: int, rest_before: float) -> float:
        """
        Compute metabolic drive chi from rep count and rest
        """
        rep_factor = 1 + 0.05 * rep_num
        rest_factor = math.exp(-rest_before / 60)  # 60s characteristic time
        return rep_factor * rest_factor
    
    def update_rep_level(
        self,
        state: RepLevelState,
        weight: float,
        v_obs: float,
        v_ref: float,
        rep_num: int,
        rest_before: float,
        is_legs: bool = False,
        capacity: Optional[float] = None
    ) -> RepLevelState:
        """
        Update rep-level state after a rep
        
        Args:
            state: Current rep-level state
            weight: Weight lifted (kg)
            v_obs: Observed velocity (m/s)
            v_ref: Reference velocity for this weight (m/s)
            rep_num: Repetition number in the set
            rest_before: Rest time before this rep (seconds)
            is_legs: Whether this is a leg exercise
            capacity: Athlete's capacity (e1RM) for this lift. If None, uses 100kg default.
        """
        p = self.params
        
        # Compute drives using capacity-based intensity
        if capacity is None or capacity <= 0:
            capacity = 100.0  # Fallback default
        intensity = min(0.95, weight / capacity)
        v_ratio = v_ref / max(v_obs, 0.01)
        phi = self.compute_phi(intensity, v_ratio)
        chi = self.compute_chi(rep_num, rest_before)
        
        # Update states (equations from spec)
        new_x_l = state.x_l - p.alpha_l * phi * (1 + p.etaM * state.M)
        new_x_sys = state.x_sys - p.alpha_sys * phi
        new_M = state.M + p.alpha_M * chi
        
        return RepLevelState(x_l=new_x_l, x_sys=new_x_sys, M=new_M)
    
    def recover_during_rest(
        self,
        state: RepLevelState,
        delta_t: float,
        R_mito: float
    ) -> RepLevelState:
        """
        Recover during rest period
        delta_t: rest time in seconds
        R_mito: current recovery capacity
        """
        p = self.params
        
        # Local recovery
        tau_eff_l = p.tau_rest_l / (1 + p.beta_rest * R_mito)
        recovery_l = p.r_l * (1 - math.exp(-delta_t / tau_eff_l)) * (1 + p.beta_rest * R_mito)
        new_x_l = state.x_l + recovery_l - p.etaMrest * state.M
        
        # System recovery
        tau_eff_sys = p.tau_rest_sys / (1 + p.beta_rest * R_mito)
        recovery_sys = p.r_sys * (1 - math.exp(-delta_t / tau_eff_sys)) * (1 + p.beta_rest * R_mito)
        new_x_sys = state.x_sys + recovery_sys - p.etaMrest * state.M
        
        # Metabolic clearance
        tau_M_eff = p.tau_M / (1 + p.beta_M * R_mito)
        new_M = state.M * math.exp(-delta_t / tau_M_eff)
        
        return RepLevelState(x_l=new_x_l, x_sys=new_x_sys, M=new_M)
    
    def initialize_rep_state(
        self,
        day_state: DayLevelState,
        lift: LiftType,
        M_base: float = 0.0
    ) -> RepLevelState:
        """
        Initialize rep-level state at start of session
        """
        D_l = day_state.D_l.get(lift, 0.0)
        A_l = max(0.05, 1 - D_l)
        A_sys = max(0.05, 1 - day_state.D_sys)
        M = M_base
        
        return RepLevelState(
            x_l=math.log(A_l),
            x_sys=math.log(A_sys),
            M=M
        )
    
    def compute_strength_impulse(
        self,
        tonnage: float,
        avg_intensity: float,
        avg_velocity_factor: float,
        is_legs: bool = False
    ) -> float:
        """
        Compute daily strength impulse u_l
        """
        base_impulse = tonnage * avg_intensity * avg_velocity_factor
        leg_factor = 1.2 if is_legs else 1.0
        return base_impulse * leg_factor
    
    def compute_endurance_splits(
        self,
        duration: float,  # minutes
        intensity_type: EnduranceIntensity,
        sport: EnduranceSport
    ) -> Tuple[float, float]:
        """
        Split endurance work into Z2 (R_mito) and HIIT (E_fat) components
        Returns: (u_E_Z2, u_E_HIIT)
        """
        if intensity_type == EnduranceIntensity.Z2:
            return duration, 0.0
        elif intensity_type == EnduranceIntensity.HIIT:
            return 0.0, duration
        else:
            # Mixed - simple split
            return duration * 0.3, duration * 0.7
    
    def compute_interference_factor(
        self,
        sport: EnduranceSport,
        hours_before_strength: float
    ) -> float:
        """
        Compute timing-based interference factor
        """
        # Mode factor
        mode_factors = {
            EnduranceSport.RUNNING: 1.0,
            EnduranceSport.CYCLING: 0.6,
            EnduranceSport.SWIMMING: 0.3
        }
        mode_factor = mode_factors.get(sport, 0.5)
        
        # Timing factor (peaks <24h)
        if hours_before_strength < 0:
            timing_factor = 0.0  # After strength
        elif hours_before_strength > 48:
            timing_factor = 0.1
        elif hours_before_strength > 24:
            timing_factor = 0.5
        else:
            timing_factor = 1.0 + (24 - hours_before_strength) / 24
        
        return mode_factor * timing_factor
    
    def update_day_state(
        self,
        current: DayLevelState,
        strength_impulses: Dict[LiftType, float],
        u_E_Z2: float,
        u_E_HIIT: float,
        u_E_total: float,
        interference_factors: Dict[LiftType, float]
    ) -> DayLevelState:
        """
        Update day-level states with all coupling
        """
        p = self.params
        new_date = current.date  # Should be incremented by caller
        
        # Compute effective time constants with R_mito
        tau_Dl_eff = lambda: p.tau_Dl / (1 + p.beta_l * current.R_mito)
        tau_Sys_eff = p.tau_Sys / (1 + p.beta_sys * current.R_mito)
        
        # Update per-lift states
        new_D_l = {}
        for lift in LiftType:
            u_l = strength_impulses.get(lift, 0.0)
            interf = p.k_ES_squat * u_E_HIIT * interference_factors.get(lift, 0.0)
            if lift != LiftType.SQUAT:
                # Scale interference by lift-specific factor
                interf *= getattr(p, f'k_ES_{lift.value}', 0.001) / p.k_ES_squat
            
            D_l_decay = current.D_l.get(lift, 0.0) * math.exp(-1 / tau_Dl_eff())
            new_D_l[lift] = D_l_decay + p.k_Dl * u_l + interf
        
        # Update system fatigue
        u_sys = sum(strength_impulses.values())
        D_sys_decay = current.D_sys * math.exp(-1 / tau_Sys_eff)
        interf_sys = p.k_ES_squat * u_E_HIIT * 0.5  # Avg interference
        new_D_sys = D_sys_decay + p.k_Sys * u_sys + interf_sys
        
        # Update R_mito (recovery capacity)
        R_mito_decay = current.R_mito * math.exp(-1 / p.tau_mito)
        new_R_mito = R_mito_decay + p.k_mito * u_E_Z2
        new_R_mito = min(2.0, new_R_mito)  # Cap at 2x baseline
        
        # Update endurance fatigue
        E_fat_decay = current.E_fat * math.exp(-1 / p.tau_Efat)
        u_legs = strength_impulses.get(LiftType.SQUAT, 0.0) + \
                 strength_impulses.get(LiftType.DEADLIFT, 0.0) * 0.5
        new_E_fat = E_fat_decay + p.k_EHIIT * u_E_HIIT + p.k_SE * u_legs
        
        new_state = DayLevelState(
            date=new_date,
            D_l=new_D_l,
            F_l=current.F_l,  # V1: fitness updates not implemented
            C_l=current.C_l,  # V1: capacity updates not implemented
            D_sys=new_D_sys,
            R_mito=new_R_mito,
            E_fat=new_E_fat
        )
        
        return new_state
    
    def compute_M_base(self, u_E_total: float, u_S_metabolic: float) -> float:
        """
        Compute base metabolic state from chronic endurance/strength work
        """
        return self.params.theta * u_E_total + self.params.zeta * u_S_metabolic


class Autoregulator:
    """Live autoregulation suggestions based on rep-level state"""
    
    def __init__(self, model: ConcurrentTrainingModel):
        self.model = model
        self.params = model.params
    
    def suggest_action(
        self,
        state: RepLevelState,
        target_v_low: float,
        target_v_high: float,
        vl_max: float,
        v_ref: float,
        current_reps_done: int,
        planned_reps: int,
        current_weight: float
    ) -> Dict:
        """
        Generate autoregulation suggestion
        """
        v_pred = state.predict_velocity(v_ref, self.params.kM)
        vl_current = (v_ref - v_pred) / v_ref * 100 if v_pred > 0 else 100
        
        action = {
            "continue": True,
            "message": [],
            "load_change": 0.0,
            "rest_suggestion": None,
            "exercise_switch": None
        }
        
        # Check stop conditions
        if vl_current > vl_max:
            action["continue"] = False
            action["message"].append(f"Velocity loss {vl_current:.1f}% exceeds limit {vl_max}%")
            return action
        
        v_floor = v_ref * self.params.v_floor_pct
        if v_pred < v_floor:
            action["continue"] = False
            action["message"].append(f"Predicted velocity {v_pred:.2f} m/s below floor {v_floor:.2f}")
            return action
        
        # Load adjustment based on first rep performance
        if current_reps_done == 0:
            if v_pred < target_v_low:
                action["load_change"] = -0.025  # -2.5%
                action["message"].append(f"Velocity low ({v_pred:.2f}), reduce load 2.5%")
            elif v_pred > target_v_high and vl_current < 10:
                action["load_change"] = 0.025  # +2.5%
                action["message"].append(f"Velocity high ({v_pred:.2f}) with low VL, increase load 2.5%")
        
        # Check limiting factors
        A_l = state.A_l
        A_sys = state.A_sys
        M = state.M
        
        if A_sys < 0.6 and A_sys < A_l:
            action["rest_suggestion"] = "Increase rest - system fatigue limiting"
            action["message"].append("System availability low, consider longer rest")
        
        if A_l < 0.5:
            action["message"].append("Local availability low, consider deload")
        
        if A_sys < 0.4:
            action["exercise_switch"] = "Switch to lighter compounds - system collapsed"
            action["message"].append("System fatigue critical, switch exercise")
        
        if M > 1.5:
            action["message"].append("Metabolic limitation high")
        
        return action
    
    def compute_readiness(
        self,
        day_state: DayLevelState,
        lift: Optional[LiftType] = None
    ) -> Dict:
        """
        Compute readiness scores with explanations
        """
        readiness = {
            "overall": 0.0,
            "per_lift": {},
            "endurance": 0.0,
            "explanations": []
        }
        
        # Per-lift readiness
        for l in LiftType:
            D_l = day_state.D_l.get(l, 0.0)
            D_sys = day_state.D_sys
            
            # Combined availability
            avail = (1 - D_l) * (1 - D_sys) * (1 + 0.3 * day_state.R_mito)
            readiness["per_lift"][l.value] = round(max(0, min(100, avail * 100)), 1)
        
        # Overall readiness (weighted average)
        if lift:
            readiness["overall"] = readiness["per_lift"][lift.value]
        else:
            avg = sum(readiness["per_lift"].values()) / len(readiness["per_lift"])
            readiness["overall"] = round(avg, 1)
        
        # Endurance readiness
        end_avail = (1 - day_state.E_fat) * (1 + 0.2 * day_state.R_mito)
        readiness["endurance"] = round(max(0, min(100, end_avail * 100)), 1)
        
        # Generate explanations
        explanations = []
        
        # Top fatigue contributors
        sorted_lifts = sorted(
            day_state.D_l.items(),
            key=lambda x: x[1],
            reverse=True
        )
        if sorted_lifts[0][1] > 0.3:
            explanations.append(f"{sorted_lifts[0][0].value} has highest fatigue ({sorted_lifts[0][1]:.2f})")
        
        if day_state.D_sys > 0.4:
            explanations.append(f"System fatigue elevated ({day_state.D_sys:.2f})")
        
        if day_state.R_mito > 0.5:
            explanations.append(f"Recovery capacity enhanced ({day_state.R_mito:.2f})")
        elif day_state.R_mito < 0.2:
            explanations.append("Recovery capacity low - consider Z2 work")
        
        if day_state.E_fat > 0.4:
            explanations.append(f"Endurance fatigue high ({day_state.E_fat:.2f})")
        
        readiness["explanations"] = explanations
        
        return readiness
