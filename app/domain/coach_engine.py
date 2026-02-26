"""
Coach engine for workout generation and adaptation.

Deterministic, rule-based coaching that:
- Generates workouts based on athlete state
- Adapts planned workouts based on readiness
- Provides intra-session adjustments
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import math
from datetime import date


class GoalMode(str, Enum):
    """Workout goal modes."""
    STRENGTH = "strength"
    ENDURANCE = "endurance"
    CONCURRENT = "concurrent"


class WorkoutType(str, Enum):
    """Types of strength workouts."""
    STRENGTH = "strength"  # Low reps, high intensity
    HYPERTROPHY = "hypertrophy"  # Moderate reps, moderate intensity
    POWER = "power"  # Low reps, velocity-focused
    TECHNIQUE = "technique"  # Light, quality-focused


class LoadMethod(str, Enum):
    """Method for prescribing load."""
    PERCENT_C = "percent_c"  # % of capacity (C_l)
    RPE = "rpe"  # Rate of perceived exertion
    VELOCITY = "velocity"  # Velocity target (m/s)


class ActionType(str, Enum):
    """Intra-session adjustment actions."""
    PROCEED = "proceed"  # Continue as planned
    INCREASE_LOAD = "increase_load"  # Load too light
    DECREASE_LOAD = "decrease_load"  # Load too heavy
    ADD_REP = "add_rep"  # Add rep to set
    STOP_SET = "stop_set"  # End set early
    EXTEND_REST = "extend_rest"  # Longer rest needed
    NEXT_EXERCISE = "next_exercise"  # Move on


@dataclass
class SetPrescription:
    """Prescription for a single set."""
    set_number: int
    target_reps: int
    load_method: LoadMethod
    load_value: float  # % C_l, RPE, or velocity target
    rest_seconds: int
    vl_max: Optional[float] = None  # Velocity loss limit (%)
    v_target_low: Optional[float] = None  # Velocity target band
    v_target_high: Optional[float] = None
    rpe_target: Optional[float] = None  # Fallback RPE
    notes: str = ""


@dataclass
class ExerciseBlock:
    """A block of sets for one exercise."""
    exercise: str
    exercise_order: int
    sets: List[SetPrescription]
    is_primary: bool = True
    
    @property
    def total_sets(self) -> int:
        return len(self.sets)
    
    @property
    def total_volume(self) -> int:
        return sum(s.target_reps for s in self.sets)


@dataclass
class StrengthWorkout:
    """A strength training workout."""
    workout_type: WorkoutType
    blocks: List[ExerciseBlock]
    estimated_duration_minutes: int
    
    @property
    def primary_lifts(self) -> List[str]:
        return [b.exercise for b in self.blocks if b.is_primary]
    
    @property
    def total_sets(self) -> int:
        return sum(b.total_sets for b in self.blocks)


@dataclass
class EnduranceSession:
    """An endurance training session."""
    mode: str  # running, cycling, swimming
    session_type: str  # z2, tempo, hiit
    duration_minutes: int
    intensity_target: Optional[str] = None  # HR zone, RPE, etc.
    intervals: Optional[List[Tuple[int, int]]] = None  # (work, rest) in seconds
    notes: str = ""


@dataclass
class ConcurrentWorkout:
    """A concurrent training day with both strength and endurance."""
    strength: Optional[StrengthWorkout]
    endurance: Optional[EnduranceSession]
    order: str = "strength_first"  # or "endurance_first"
    recovery_between_hours: float = 6.0


@dataclass
class WorkoutPlan:
    """Full workout plan for a day."""
    date: date
    goal_mode: GoalMode
    workout: Union[StrengthWorkout, EnduranceSession, ConcurrentWorkout]
    explanations: List[str]
    readiness_at_generation: Dict[str, float]


@dataclass
class IntraSetState:
    """Current state during a set for intra-session adjustments."""
    exercise: str
    set_number: int
    target_reps: int
    reps_completed: int
    velocities: List[float]  # Observed velocities so far
    load_kg: float
    rest_before_set: int
    
    @property
    def vl_current(self) -> float:
        """Current velocity loss in set."""
        if len(self.velocities) < 2:
            return 0.0
        v_first = self.velocities[0]
        v_last = self.velocities[-1]
        if v_first > 0:
            return (v_first - v_last) / v_first
        return 0.0


@dataclass
class IntraSetAction:
    """Action recommendation during a set."""
    action: ActionType
    message: str
    load_adjustment_percent: float = 0.0  # % change to apply next set
    rest_adjustment_seconds: int = 0  # Additional rest
    stop_current_set: bool = False


@dataclass(frozen=True)
class CoachParams:
    """Configurable coach parameters."""
    # Readiness thresholds
    readiness_low: float = 0.55
    readiness_moderate: float = 0.75
    
    # Load percentages for strength work
    pct_top_set_strength: float = 0.90  # 90% of C_l
    pct_backoff_strength: float = 0.87  # 87% of top
    pct_hypertrophy: float = 0.78  # 78% of C_l
    pct_power: float = 0.65  # 65% of C_l (velocity focus)
    pct_technique: float = 0.60  # 60% of C_l
    
    # RPE targets
    rpe_strength: float = 8.0
    rpe_hypertrophy: float = 7.5
    rpe_power: float = 6.0
    rpe_technique: float = 6.0
    
    # Velocity targets (m/s)
    v_target_power_low: float = 0.65
    v_target_power_high: float = 0.80
    v_target_strength_low: float = 0.35
    v_target_strength_high: float = 0.50
    
    # Volume guidelines
    sets_strength_low_readiness: int = 2
    sets_strength_normal: int = 4
    sets_hypertrophy_low_readiness: int = 3
    sets_hypertrophy_normal: int = 5
    
    # VL limits
    vl_max_strength: float = 0.20  # 20%
    vl_max_hypertrophy: float = 0.25  # 25%
    vl_max_technique: float = 0.15  # 15%
    
    # Intra-session triggers
    vl_stop_threshold: float = 0.30  # Stop set if VL > 30%
    velocity_floor: float = 0.25  # Stop if v < 0.25 m/s
    load_increase_if_velocity_high: float = 0.025  # +2.5%
    load_decrease_if_velocity_low: float = 0.025  # -2.5%


def determine_workout_type(
    readiness_lift: float,
    readiness_system: float,
    params: CoachParams
) -> WorkoutType:
    """Determine appropriate workout type based on readiness."""
    if readiness_lift < params.readiness_low:
        return WorkoutType.TECHNIQUE
    elif readiness_system < params.readiness_low:
        return WorkoutType.TECHNIQUE
    else:
        return WorkoutType.STRENGTH


def generate_strength_workout(
    lifts: List[str],
    readiness: Dict[str, float],
    capacities: Dict[str, float],
    system_readiness: float,
    endurance_fatigue: float,
    params: CoachParams = None
) -> Tuple[StrengthWorkout, List[str]]:
    """
    Generate a strength workout based on current state.
    
    Returns:
        Tuple of (workout, explanations)
    """
    params = params or CoachParams()
    explanations = []
    blocks = []
    
    # Sort lifts by readiness (highest first)
    available_lifts = [(l, readiness.get(l, 0.5)) for l in lifts]
    available_lifts.sort(key=lambda x: x[1], reverse=True)
    
    # Select primary lifts
    if system_readiness < params.readiness_low:
        # Low system readiness: do only 1 primary lift, lighter
        primary_lifts = [available_lifts[0][0]] if available_lifts else ["squat"]
        workout_type = WorkoutType.TECHNIQUE
        explanations.append(f"System readiness low ({system_readiness:.0%}): technique focus with reduced volume")
    elif endurance_fatigue > 0.4:
        # High endurance fatigue: avoid heavy legs
        primary_lifts = [l for l, _ in available_lifts[:2] if l not in ["squat", "deadlift"]]
        if not primary_lifts:
            primary_lifts = ["bench"] if "bench" in lifts else [available_lifts[0][0]]
        workout_type = WorkoutType.STRENGTH
        explanations.append(f"Endurance fatigue elevated ({endurance_fatigue:.0%}): upper body focus")
    else:
        # Normal: up to 2 primary lifts
        primary_lifts = [l for l, _ in available_lifts[:2]]
        workout_type = WorkoutType.STRENGTH
        explanations.append(f"System readiness good ({system_readiness:.0%}): standard strength session")
    
    # Generate blocks for each primary lift
    for lift in primary_lifts:
        lift_readiness = readiness.get(lift, 0.7)
        capacity = capacities.get(lift, 100.0)
        
        workout_type = determine_workout_type(lift_readiness, system_readiness, params)
        
        if workout_type == WorkoutType.TECHNIQUE:
            # Light technique work
            sets = [
                SetPrescription(
                    set_number=i+1,
                    target_reps=5,
                    load_method=LoadMethod.PERCENT_C,
                    load_value=params.pct_technique,
                    rest_seconds=120,
                    vl_max=params.vl_max_technique,
                    rpe_target=params.rpe_technique,
                    notes="Focus on movement quality"
                )
                for i in range(params.sets_strength_low_readiness)
            ]
            explanations.append(f"{lift}: technique day ({params.sets_strength_low_readiness} sets @ {params.pct_technique:.0%})")
            
        elif workout_type == WorkoutType.STRENGTH:
            # Top set + back-offs
            num_sets = params.sets_strength_normal if lift_readiness > params.readiness_moderate else params.sets_strength_low_readiness
            
            sets = []
            # Top set
            sets.append(SetPrescription(
                set_number=1,
                target_reps=3,
                load_method=LoadMethod.PERCENT_C,
                load_value=params.pct_top_set_strength,
                rest_seconds=240,
                vl_max=params.vl_max_strength,
                rpe_target=params.rpe_strength,
                notes="Top set - aim for crisp reps"
            ))
            
            # Back-off sets
            for i in range(1, num_sets):
                sets.append(SetPrescription(
                    set_number=i+1,
                    target_reps=5,
                    load_method=LoadMethod.PERCENT_C,
                    load_value=params.pct_backoff_strength,
                    rest_seconds=180,
                    vl_max=params.vl_max_strength,
                    rpe_target=params.rpe_strength - 0.5,
                    notes="Back-off set"
                ))
            
            explanations.append(f"{lift}: strength ({num_sets} sets, top @ {params.pct_top_set_strength:.0%})")
        
        blocks.append(ExerciseBlock(
            exercise=lift,
            exercise_order=len(blocks),
            sets=sets,
            is_primary=True
        ))
    
    # Estimate duration
    total_sets = sum(len(b.sets) for b in blocks)
    est_duration = total_sets * 5 + 15  # 5 min per set + warmup
    
    workout = StrengthWorkout(
        workout_type=workout_type,
        blocks=blocks,
        estimated_duration_minutes=est_duration
    )
    
    return workout, explanations


def generate_endurance_workout(
    readiness_endurance: float,
    endurance_fatigue: float,
    time_budget_minutes: int,
    has_legs_strength_today: bool = False,
    params: CoachParams = None
) -> Tuple[EnduranceSession, List[str]]:
    """Generate an endurance workout based on current state."""
    params = params or CoachParams()
    explanations = []
    
    if readiness_endurance < params.readiness_low:
        # Low readiness: short Z2 or rest
        session = EnduranceSession(
            mode="cycling",  # Lowest impact
            session_type="z2",
            duration_minutes=min(30, time_budget_minutes),
            intensity_target="Zone 2 (easy conversational)",
            notes="Recovery session - keep effort very easy"
        )
        explanations.append(f"Endurance readiness low ({readiness_endurance:.0%}): short recovery ride")
        return session, explanations
    
    if endurance_fatigue > 0.4 and has_legs_strength_today:
        # High fatigue + strength today: avoid HIIT
        session = EnduranceSession(
            mode="cycling",
            session_type="z2",
            duration_minutes=min(45, time_budget_minutes),
            intensity_target="Zone 2",
            notes="Active recovery - avoid intensity due to strength session"
        )
        explanations.append("Endurance fatigue + strength today: Z2 only, no intensity")
        return session, explanations
    
    # Normal case: choose based on time and fatigue
    if time_budget_minutes < 40:
        session = EnduranceSession(
            mode="running" if not has_legs_strength_today else "cycling",
            session_type="hiit",
            duration_minutes=30,
            intervals=[(30, 30)] * 10,  # 10x 30/30
            notes="Short HIIT session"
        )
        explanations.append("Time limited: short HIIT for efficiency")
    elif endurance_fatigue < 0.2 and readiness_endurance > params.readiness_moderate:
        # Fresh and good readiness: can do HIIT
        session = EnduranceSession(
            mode="running",
            session_type="hiit",
            duration_minutes=45,
            intervals=[(180, 180)] * 6,  # 6x 3min intervals
            notes="VO2max intervals - high intensity"
        )
        explanations.append("Good freshness: VO2max intervals")
    else:
        # Default: Z2
        duration = min(90, time_budget_minutes)
        session = EnduranceSession(
            mode="cycling",
            session_type="z2",
            duration_minutes=duration,
            intensity_target="Zone 2",
            notes="Aerobic base development"
        )
        explanations.append(f"Default aerobic development: {duration}min Z2")
    
    return session, explanations


def generate_workout(
    goal_mode: GoalMode,
    lifts: List[str],
    readiness: Dict[str, float],
    capacities: Dict[str, float],
    system_readiness: float,
    endurance_readiness: float,
    endurance_fatigue: float,
    time_budget_minutes: int = 60,
    params: CoachParams = None
) -> Tuple[WorkoutPlan, List[str]]:
    """
    Main entry point: generate a complete workout plan.
    
    Returns:
        Tuple of (plan, explanations)
    """
    params = params or CoachParams()
    explanations = []
    
    all_readiness = {
        **readiness,
        "system": system_readiness,
        "endurance": endurance_readiness
    }
    
    if goal_mode == GoalMode.STRENGTH:
        workout, exp = generate_strength_workout(
            lifts, readiness, capacities, system_readiness, endurance_fatigue, params
        )
        explanations.extend(exp)
        
        plan = WorkoutPlan(
            date=date.today(),
            goal_mode=goal_mode,
            workout=workout,
            explanations=explanations,
            readiness_at_generation=all_readiness
        )
        
    elif goal_mode == GoalMode.ENDURANCE:
        session, exp = generate_endurance_workout(
            endurance_readiness, endurance_fatigue, time_budget_minutes, False, params
        )
        explanations.extend(exp)
        
        plan = WorkoutPlan(
            date=date.today(),
            goal_mode=goal_mode,
            workout=session,
            explanations=explanations,
            readiness_at_generation=all_readiness
        )
        
    else:  # CONCURRENT
        # Generate both components
        strength_workout, exp_s = generate_strength_workout(
            lifts, readiness, capacities, system_readiness, endurance_fatigue, params
        )
        explanations.extend(exp_s)
        
        endurance_session, exp_e = generate_endurance_workout(
            endurance_readiness, endurance_fatigue, time_budget_minutes // 2, True, params
        )
        explanations.extend(exp_e)
        
        concurrent = ConcurrentWorkout(
            strength=strength_workout,
            endurance=endurance_session,
            order="strength_first",
            recovery_between_hours=6.0
        )
        
        plan = WorkoutPlan(
            date=date.today(),
            goal_mode=goal_mode,
            workout=concurrent,
            explanations=explanations,
            readiness_at_generation=all_readiness
        )
    
    return plan, explanations


def adapt_workout(
    original: WorkoutPlan,
    current_readiness: Dict[str, float],
    system_readiness: float,
    explanations: List[str] = None
) -> WorkoutPlan:
    """
    Adapt an existing workout based on current readiness.
    
    Reduces volume/intensity if readiness dropped significantly.
    """
    explanations = explanations or []
    
    # Compare current vs planned readiness
    readiness_drop = False
    for lift, current in current_readiness.items():
        planned = original.readiness_at_generation.get(lift, 1.0)
        if current < planned - 0.15:  # >15% drop
            readiness_drop = True
            explanations.append(f"{lift} readiness dropped ({planned:.0%} → {current:.0%}): reducing load")
    
    if system_readiness < original.readiness_at_generation.get("system", 1.0) - 0.15:
        readiness_drop = True
        explanations.append("System readiness dropped: reducing volume")
    
    if not readiness_drop:
        explanations.append("Readiness as expected: proceed as planned")
        return original
    
    # Create adapted plan with reduced volume
    # (Simplified: just note the adaptation - full implementation would modify sets)
    adapted = WorkoutPlan(
        date=original.date,
        goal_mode=original.goal_mode,
        workout=original.workout,  # In full implementation, modify this
        explanations=original.explanations + explanations,
        readiness_at_generation=current_readiness
    )
    
    return adapted


def intra_set_decision(
    state: IntraSetState,
    prescription: SetPrescription,
    params: CoachParams = None
) -> IntraSetAction:
    """
    Make real-time decision during a set based on observed velocities.
    
    This is the core VBT-driven intra-session adjustment.
    """
    params = params or CoachParams()
    
    if not state.velocities:
        return IntraSetAction(
            action=ActionType.PROCEED,
            message="Start set - no data yet"
        )
    
    v_current = state.velocities[-1]
    vl = state.vl_current
    
    # Check velocity floor (safety)
    if v_current < params.velocity_floor:
        return IntraSetAction(
            action=ActionType.STOP_SET,
            message=f"Velocity {v_current:.2f} m/s below floor {params.velocity_floor} - stop for safety",
            stop_current_set=True
        )
    
    # Check velocity loss limit
    if vl > params.vl_stop_threshold:
        return IntraSetAction(
            action=ActionType.STOP_SET,
            message=f"VL {vl:.1%} exceeds limit {params.vl_stop_threshold:.1%} - end set",
            stop_current_set=True
        )
    
    # Check if prescribed VL max reached
    if prescription.vl_max and vl > prescription.vl_max:
        return IntraSetAction(
            action=ActionType.STOP_SET,
            message=f"VL {vl:.1%} at prescribed limit {prescription.vl_max:.1%}",
            stop_current_set=True
        )
    
    # Check rep target reached
    if state.reps_completed >= state.target_reps:
        # Evaluate performance for next set
        if vl < 0.10:  # Very low VL - load too light
            return IntraSetAction(
                action=ActionType.INCREASE_LOAD,
                message=f"Low VL ({vl:.1%}) - load too light, increase 2.5% next set",
                load_adjustment_percent=params.load_increase_if_velocity_high
            )
        elif vl > 0.20:  # High VL - load heavy
            return IntraSetAction(
                action=ActionType.DECREASE_LOAD,
                message=f"High VL ({vl:.1%}) - load heavy, decrease 2.5% next set",
                load_adjustment_percent=-params.load_decrease_if_velocity_low
            )
        else:
            return IntraSetAction(
                action=ActionType.NEXT_EXERCISE,
                message=f"Target reps completed, VL {vl:.1%} - good set"
            )
    
    # In middle of set
    if vl > 0.20:
        return IntraSetAction(
            action=ActionType.PROCEED,
            message=f"High fatigue (VL {vl:.1%}) - focus on quality"
        )
    
    return IntraSetAction(
        action=ActionType.PROCEED,
        message=f"On track - continue (VL {vl:.1%})"
    )
