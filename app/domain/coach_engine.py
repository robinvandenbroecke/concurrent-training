"""
Coach engine for workout generation and adaptation.

Deterministic, rule-based coaching that:
- Generates workouts based on athlete state
- Adapts planned workouts based on readiness
- Provides intra-session adjustments
- Minimizes interference in concurrent training
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
    PERCENT_C = "percent_capacity"  # % of capacity (C_l)
    RPE = "rpe"  # Rate of perceived exertion
    VELOCITY = "velocity"  # Velocity target (m/s)


class ActionType(str, Enum):
    """Intra-session adjustment actions."""
    PROCEED = "proceed"  # Continue as planned
    INCREASE_LOAD = "increase_load"  # Load too light
    DECREASE_LOAD = "decrease_load"  # Load too heavy
    ADD_SET = "add_set"  # Add a set
    DROP_SET = "drop_set"  # Remove last set
    STOP_SET = "stop_set"  # End set early
    EXTEND_REST = "extend_rest"  # Longer rest needed
    NEXT_EXERCISE = "next_exercise"  # Move on
    SWITCH_TO_TECHNIQUE = "switch_to_technique"  # Change intent


class LimitingFactor(str, Enum):
    """Primary limiting factor during exercise."""
    LOCAL = "local"  # Local muscular fatigue
    CENTRAL = "central"  # System/CNS fatigue
    METABOLIC = "metabolic"  # Metabolic limitation


@dataclass
class DayStateSnapshot:
    """Snapshot of day state for coach decisions."""
    readiness_per_lift: Dict[str, float]
    readiness_endurance: float
    D_sys: float  # System fatigue
    E_fat: float  # Endurance fatigue
    R_mito: float  # Recovery capacity
    capacities_per_lift: Dict[str, float]
    date: date


@dataclass
class SetPrescription:
    """Prescription for a single set."""
    set_number: int
    target_reps: Union[int, Tuple[int, int]]
    load_method: LoadMethod
    target_value: Union[float, Tuple[float, float]]
    rest_seconds: int
    vl_max: Optional[float] = None
    v_target: Optional[Tuple[float, float]] = None
    rpe_target: Optional[float] = None
    notes: str = ""


@dataclass
class ExerciseBlock:
    """A block of sets for one exercise."""
    lift: str
    intent: str  # "power"|"strength"|"volume"|"technique"
    prescription: SetPrescription
    completed_sets: int = 0
    
    @property
    def total_sets(self) -> int:
        return self.prescription.sets if isinstance(self.prescription.sets, int) else 0


@dataclass
class StrengthWorkout:
    """A strength training workout."""
    blocks: List[ExerciseBlock]
    notes: List[str] = field(default_factory=list)
    
    @property
    def primary_lifts(self) -> List[str]:
        return [b.lift for b in self.blocks]


@dataclass
class EnduranceWorkout:
    """An endurance training session."""
    sport: str  # cycling/running/swimming
    intent: str  # z2/tempo/hiit
    duration_min: int
    structure: List[Dict] = field(default_factory=list)  # intervals
    targets: Dict = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


@dataclass
class ConcurrentWorkout:
    """A concurrent training day."""
    strength: Optional[StrengthWorkout]
    endurance: Optional[EnduranceWorkout]
    order: str = "strength_first"  # or "endurance_first"
    notes: List[str] = field(default_factory=list)


@dataclass
class WorkoutPlan:
    """Full workout plan for a day."""
    date: str
    mode: str
    workout: Union[StrengthWorkout, EnduranceWorkout, ConcurrentWorkout]
    explanations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "mode": self.mode,
            "explanations": self.explanations,
            "workout": self._workout_to_dict()
        }
    
    def _workout_to_dict(self) -> dict:
        """Serialize workout based on type."""
        if isinstance(self.workout, StrengthWorkout):
            return {
                "type": "strength",
                "blocks": [
                    {
                        "lift": b.lift,
                        "intent": b.intent,
                        "prescription": {
                            "reps": b.prescription.target_reps if isinstance(b.prescription.target_reps, int) else list(b.prescription.target_reps),
                            "load_method": b.prescription.load_method.value,
                            "target": b.prescription.target_value,
                            "rest_sec": b.prescription.rest_seconds,
                            "vl_max": b.prescription.vl_max,
                        }
                    }
                    for b in self.workout.blocks
                ],
                "notes": self.workout.notes
            }
        elif isinstance(self.workout, EnduranceWorkout):
            return {
                "type": "endurance",
                "sport": self.workout.sport,
                "intent": self.workout.intent,
                "duration_min": self.workout.duration_min,
                "structure": self.workout.structure,
                "targets": self.workout.targets,
                "notes": self.workout.notes
            }
        elif isinstance(self.workout, ConcurrentWorkout):
            # Recursively serialize
            strength_dict = None
            if self.workout.strength:
                strength_plan = WorkoutPlan(self.date, "strength", self.workout.strength, [])
                strength_dict = strength_plan._workout_to_dict()
            
            endurance_dict = None
            if self.workout.endurance:
                endurance_plan = WorkoutPlan(self.date, "endurance", self.workout.endurance, [])
                endurance_dict = endurance_plan._workout_to_dict()
            
            return {
                "type": "concurrent",
                "order": self.workout.order,
                "strength": strength_dict,
                "endurance": endurance_dict,
                "notes": self.workout.notes
            }
        return {}


@dataclass
class IntraSetState:
    """Current state during a set for intra-session adjustments."""
    exercise: str
    set_number: int
    target_reps: int
    reps_completed: int
    velocities: List[float]
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
    
    @property
    def v_current(self) -> float:
        """Most recent velocity."""
        return self.velocities[-1] if self.velocities else 0.0


@dataclass
class NextSetAdjustment:
    """Result of intra-set decision."""
    updated_block: ExerciseBlock
    action: ActionType
    explanation: str
    stop_current_set: bool = False


@dataclass(frozen=True)
class CoachParams:
    """Configurable coach parameters."""
    # Readiness thresholds
    readiness_low: float = 0.55
    readiness_moderate: float = 0.75
    readiness_high: float = 0.80
    
    # Load scaling for adaptation
    scale_readiness_low: float = 0.85
    scale_readiness_moderate: float = 0.92
    scale_readiness_good: float = 0.97
    scale_readiness_high: float = 1.025  # +2.5%
    
    # Preset templates
    presets: Dict = field(default_factory=lambda: {
        "strength": {
            "sets": 4,
            "reps": (2, 5),
            "load": (0.88, 0.93),  # % of C_l
            "rest": 240,
            "vl_max": 0.20,
        },
        "power": {
            "sets": 6,
            "reps": (1, 3),
            "load": (0.60, 0.75),
            "rest": 180,
            "vl_max": 0.15,
        },
        "volume": {
            "sets": 5,
            "reps": (6, 10),
            "load": (0.72, 0.80),
            "rest": 150,
            "vl_max": 0.25,
        },
        "technique": {
            "sets": 3,
            "reps": (3, 5),
            "load": (0.55, 0.70),
            "rest": 120,
            "vl_max": 0.15,
        }
    })
    
    # Sport mode interference ranking (lower = less interference)
    sport_interference: Dict[str, float] = field(default_factory=lambda: {
        "swimming": 0.6,
        "cycling": 1.0,
        "running": 1.3,
    })
    
    # Endurance zones
    endurance_zones: Dict = field(default_factory=lambda: {
        "z2": {"rpe": (2, 4), "duration": (30, 120)},
        "tempo": {"rpe": (5, 7), "duration": (20, 45)},
        "hiit": {"rpe": (8, 10), "duration": (15, 35)},
    })
    
    # Intra-set thresholds
    vl_max_stop: float = 0.30
    velocity_floor: float = 0.25
    vl_high: float = 0.20
    vl_low: float = 0.10


@dataclass
class CoachRequest:
    """Request for workout generation."""
    athlete_id: str
    date: str
    mode: str
    time_budget_min: int
    priority: Optional[str] = None  # "strength" or "endurance"
    available_sports: List[str] = field(default_factory=lambda: ["cycling", "running", "swimming"])
    vbt_available: bool = True
    preferences: Dict = field(default_factory=dict)


def determine_intent(readiness: float, D_sys: float, E_fat: float, params: CoachParams) -> str:
    """Determine workout intent based on state."""
    if readiness < params.readiness_low or D_sys > 0.5:
        return "technique"
    elif readiness > params.readiness_high and E_fat < 0.3:
        return "power" if E_fat < 0.2 else "strength"
    else:
        return "volume" if E_fat < 0.3 else "strength"


def scale_load_factor(readiness: float, params: CoachParams) -> float:
    """Get load scaling factor based on readiness."""
    if readiness < params.readiness_low:
        return params.scale_readiness_low
    elif readiness < params.readiness_moderate:
        return params.scale_readiness_moderate
    elif readiness < params.readiness_high:
        return params.scale_readiness_good
    else:
        return params.scale_readiness_high


def select_sport_mode(
    planned_strength_lifts: List[str],
    available_sports: List[str],
    E_fat: float,
    recent_modality_balance: Optional[Dict[str, int]] = None,
    params: CoachParams = None
) -> str:
    """
    Select endurance sport mode to minimize interference.
    
    Args:
        planned_strength_lifts: Which lifts are planned (affects legs interference)
        available_sports: Which sports are available to athlete
        E_fat: Current endurance fatigue
        recent_modality_balance: Recent sport distribution (optional)
        params: Coach parameters
    
    Returns:
        Selected sport mode
    """
    params = params or CoachParams()
    
    # Check if heavy legs are planned
    heavy_legs = any(lift in planned_strength_lifts for lift in ["squat", "deadlift"])
    
    # Score each available sport
    scores = {}
    for sport in available_sports:
        score = 0.0
        
        # Base interference score (lower is better for concurrent)
        interference = params.sport_interference.get(sport, 1.0)
        if heavy_legs:
            score += interference * 2.0  # Penalize high interference when legs planned
        else:
            score += interference * 0.5  # Less important when no legs
        
        # Modality balance bonus (prefer underused sports)
        if recent_modality_balance and sport in recent_modality_balance:
            usage = recent_modality_balance[sport]
            total = sum(recent_modality_balance.values())
            if total > 0:
                usage_ratio = usage / total
                score += usage_ratio * 0.5  # Slight preference for variety
        
        scores[sport] = score
    
    # Select lowest score
    if scores:
        return min(scores, key=scores.get)
    return "cycling"  # Default


def determine_endurance_zone(
    readiness_endurance: float,
    E_fat: float,
    planned_strength_heavy: bool,
    params: CoachParams
) -> Tuple[str, int]:
    """
    Determine endurance zone and duration.
    
    Returns:
        Tuple of (zone, duration_minutes)
    """
    if readiness_endurance < params.readiness_low:
        # Low readiness: short Z2 only
        return ("z2", 30)
    
    if E_fat > 0.4:
        # High fatigue: Z2 only
        if planned_strength_heavy:
            return ("z2", 20)  # Very short if strength also planned
        return ("z2", 45)
    
    if readiness_endurance > params.readiness_high and E_fat < 0.2 and not planned_strength_heavy:
        # Good readiness, fresh, no heavy strength: can do HIIT
        return ("hiit", 30)
    
    if readiness_endurance > params.readiness_moderate and E_fat < 0.3:
        # Moderate: tempo
        return ("tempo", 35)
    
    # Default: Z2
    return ("z2", 60)


def generate_strength_block(
    lift: str,
    readiness: float,
    capacity: float,
    D_sys: float,
    E_fat: float,
    params: CoachParams,
    force_intent: Optional[str] = None
) -> Tuple[ExerciseBlock, List[str]]:
    """Generate a strength block for a lift."""
    explanations = []
    
    # Determine intent
    intent = force_intent or determine_intent(readiness, D_sys, E_fat, params)
    
    # Get preset
    preset = params.presets.get(intent, params.presets["technique"])
    
    # Scale load based on readiness
    load_scale = scale_load_factor(readiness, params)
    
    if isinstance(preset["load"], tuple):
        load_low, load_high = preset["load"]
        target_load = (load_low * load_scale, load_high * load_scale)
    else:
        target_load = preset["load"] * load_scale
    
    # Adjust sets based on readiness
    sets = preset["sets"]
    if readiness < params.readiness_low:
        sets = max(2, sets - 2)
        explanations.append(f"{lift}: readiness {readiness:.2f} < {params.readiness_low} → {intent}, {sets} sets")
    elif readiness < params.readiness_moderate:
        sets = max(3, sets - 1)
        explanations.append(f"{lift}: readiness {readiness:.2f} < {params.readiness_moderate} → {intent}, {sets} sets, load scaled to {load_scale:.0%}")
    elif readiness > params.readiness_high and intent == "power":
        explanations.append(f"{lift}: readiness high ({readiness:.2f}) → power focus, load {load_scale:.0%}")
    else:
        explanations.append(f"{lift}: {intent}, {sets} sets")
    
    # Create prescription
    prescription = SetPrescription(
        set_number=1,
        target_reps=preset["reps"],
        load_method=LoadMethod.PERCENT_C,
        target_value=target_load,
        rest_seconds=preset["rest"],
        vl_max=preset["vl_max"],
        notes=intent
    )
    
    block = ExerciseBlock(
        lift=lift,
        intent=intent,
        prescription=prescription
    )
    
    return block, explanations


def generate_workout(
    req: CoachRequest,
    day_state: DayStateSnapshot
) -> WorkoutPlan:
    """
    Generate a complete workout plan.
    
    Args:
        req: Coach request
        day_state: Current day state snapshot
    
    Returns:
        WorkoutPlan
    """
    params = CoachParams()
    explanations = []
    
    # Determine if heavy legs are planned
    lifts = list(day_state.readiness_per_lift.keys())
    heavy_legs_planned = any(lift in ["squat", "deadlift"] for lift in lifts)
    
    if req.mode == "strength":
        # Generate strength-only workout
        blocks = []
        for lift in lifts[:3]:  # Max 3 lifts
            readiness = day_state.readiness_per_lift.get(lift, 0.7)
            capacity = day_state.capacities_per_lift.get(lift, 100.0)
            
            block, exps = generate_strength_block(
                lift, readiness, capacity,
                day_state.D_sys, day_state.E_fat,
                params
            )
            blocks.append(block)
            explanations.extend(exps)
        
        workout = StrengthWorkout(blocks=blocks, notes=explanations)
        
        return WorkoutPlan(
            date=req.date,
            mode="strength",
            workout=workout,
            explanations=explanations
        )
    
    elif req.mode == "endurance":
        # Generate endurance-only workout
        zone, duration = determine_endurance_zone(
            day_state.readiness_endurance,
            day_state.E_fat,
            False,  # No strength planned
            params
        )
        
        sport = select_sport_mode(
            [],  # No strength lifts
            req.available_sports,
            day_state.E_fat,
            req.preferences.get("recent_sports"),
            params
        )
        
        explanations.append(f"Endurance: {zone} on {sport} for {duration}min (readiness {day_state.readiness_endurance:.2f}, E_fat {day_state.E_fat:.2f})")
        
        # Build structure based on zone
        structure = []
        if zone == "hiit":
            structure = [{"type": "interval", "work": 180, "rest": 180, "rounds": 6}]
        elif zone == "tempo":
            structure = [{"type": "steady", "duration": duration * 60}]
        else:  # z2
            structure = [{"type": "steady", "duration": duration * 60}]
        
        workout = EnduranceWorkout(
            sport=sport,
            intent=zone,
            duration_min=duration,
            structure=structure,
            targets={"rpe": params.endurance_zones[zone]["rpe"]},
            notes=explanations
        )
        
        return WorkoutPlan(
            date=req.date,
            mode="endurance",
            workout=workout,
            explanations=explanations
        )
    
    else:  # concurrent
        # Generate concurrent workout
        explanations.append(f"Concurrent mode, priority: {req.priority or 'balanced'}")
        
        # Select sport mode
        sport = select_sport_mode(
            lifts if req.priority != "endurance" else [],
            req.available_sports,
            day_state.E_fat,
            req.preferences.get("recent_sports"),
            params
        )
        
        # Determine zone based on priority and fatigue
        if req.priority == "strength":
            # Strength priority: Z2 only, minimal
            zone, duration = ("z2", 30)
            endurance_first = False
            explanations.append("Priority strength: Z2 accessory 30min")
        elif req.priority == "endurance":
            # Endurance priority: minimal strength, upper body focus
            zone, duration = determine_endurance_zone(
                day_state.readiness_endurance,
                day_state.E_fat,
                False,
                params
            )
            endurance_first = True
            explanations.append("Priority endurance: minimal strength, upper focus")
        else:
            # Balanced
            zone, duration = determine_endurance_zone(
                day_state.readiness_endurance,
                day_state.E_fat,
                heavy_legs_planned,
                params
            )
            endurance_first = False
            explanations.append(f"Balanced: strength first, {zone} endurance")
        
        # Build endurance workout
        if zone == "hiit" and heavy_legs_planned:
            # Avoid HIIT + heavy legs
            zone = "tempo"
            explanations.append("HIIT avoided due to heavy legs → tempo")
        
        endurance_workout = EnduranceWorkout(
            sport=sport,
            intent=zone,
            duration_min=duration,
            structure=[{"type": "steady" if zone in ["z2", "tempo"] else "interval", 
                       "duration": duration * 60}],
            targets={"rpe": params.endurance_zones[zone]["rpe"]},
            notes=[f"{sport} {zone}"]
        )
        
        # Build strength workout
        if req.priority == "endurance":
            # Minimal strength, upper body
            upper_lifts = [l for l in lifts if l in ["bench", "press"]]
            if not upper_lifts:
                upper_lifts = lifts[:1]  # Fallback to first lift
            
            blocks = []
            for lift in upper_lifts[:2]:
                block, exps = generate_strength_block(
                    lift,
                    day_state.readiness_per_lift.get(lift, 0.7),
                    day_state.capacities_per_lift.get(lift, 100.0),
                    day_state.D_sys, day_state.E_fat,
                    params,
                    force_intent="technique"  # Light
                )
                blocks.append(block)
                explanations.extend(exps)
        else:
            # Normal strength
            blocks = []
            for lift in lifts[:2]:  # Fewer lifts in concurrent
                block, exps = generate_strength_block(
                    lift,
                    day_state.readiness_per_lift.get(lift, 0.7),
                    day_state.capacities_per_lift.get(lift, 100.0),
                    day_state.D_sys, day_state.E_fat,
                    params
                )
                blocks.append(block)
                explanations.extend(exps)
        
        strength_workout = StrengthWorkout(blocks=blocks, notes=explanations)
        
        concurrent = ConcurrentWorkout(
            strength=strength_workout,
            endurance=endurance_workout,
            order="endurance_first" if endurance_first else "strength_first",
            notes=explanations
        )
        
        return WorkoutPlan(
            date=req.date,
            mode="concurrent",
            workout=concurrent,
            explanations=explanations
        )


def adapt_workout(
    plan: WorkoutPlan,
    day_state: DayStateSnapshot,
    is_key_session: bool = False,
    priority: str = "balanced"
) -> WorkoutPlan:
    """
    Adapt an existing workout based on current state.
    PRIORITY-AWARE: Key sessions are protected, non-key sessions downgraded freely.
    
    Args:
        plan: Original workout plan
        day_state: Current day state
        is_key_session: Whether this is a key session (must be protected)
        priority: Training priority ("strength", "endurance", "balanced")
    
    Returns:
        Adapted WorkoutPlan
    """
    params = CoachParams()
    explanations = plan.explanations.copy()
    explanations.append("--- Adaptation ---")
    
    # Priority-aware scaling factors
    if is_key_session:
        load_scale_min, load_scale_max = 0.92, 0.97
        sets_reduction_max = 1
    else:
        load_scale_min, load_scale_max = 0.80, 0.95
        sets_reduction_max = 2  # Can halve sets
    
    if plan.mode == "strength":
        adapted_blocks = []
        
        for block in plan.workout.blocks:
            lift = block.lift
            readiness = day_state.readiness_per_lift.get(lift, 0.7)
            
            # PRIORITY-AWARE adaptation
            if is_key_session:
                # Key sessions: do NOT delete, reduce load only
                if readiness < params.readiness_low:
                    # Reduce load by 5-8%, increase rest, keep session
                    load_scale = load_scale_min + (1 - readiness) * 0.03
                    new_prescription = block.prescription
                    if isinstance(new_prescription.target_value, tuple):
                        low, high = new_prescription.target_value
                        new_target = (low * load_scale, high * load_scale)
                    else:
                        new_target = new_prescription.target_value * load_scale
                    
                    new_prescription = SetPrescription(
                        set_number=new_prescription.set_number,
                        target_reps=new_prescription.target_reps,
                        load_method=new_prescription.load_method,
                        target_value=new_target,
                        rest_seconds=int(new_prescription.rest_seconds * 1.2),  # +20% rest
                        vl_max=new_prescription.vl_max,
                        notes=f"{new_prescription.notes} -load (key session)"
                    )
                    
                    adapted_blocks.append(ExerciseBlock(
                        lift=lift,
                        intent=block.intent,
                        prescription=new_prescription
                    ))
                    explanations.append(f"{lift}: KEY SESSION - load reduced {load_scale:.0%}, rest +20%")
                else:
                    adapted_blocks.append(block)
            else:
                # Non-key sessions: downgrade freely
                if readiness < params.readiness_low:
                    # Can switch to technique or reduce significantly
                    if priority == "endurance":
                        # Endurance priority: reduce strength significantly
                        new_block, exps = generate_strength_block(
                            lift, readiness,
                            day_state.capacities_per_lift.get(lift, 100.0),
                            day_state.D_sys, day_state.E_fat,
                            params,
                            force_intent="technique"
                        )
                        adapted_blocks.append(new_block)
                        explanations.extend(exps)
                        explanations.append(f"{lift}: NON-KEY → technique (endurance priority)")
                    else:
                        # Reduce load by 10-20%
                        load_scale = load_scale_min
                        new_prescription = block.prescription
                        if isinstance(new_prescription.target_value, tuple):
                            low, high = new_prescription.target_value
                            new_target = (low * load_scale, high * load_scale)
                        else:
                            new_target = new_prescription.target_value * load_scale
                        
                        new_prescription = SetPrescription(
                            set_number=new_prescription.set_number,
                            target_reps=max(3, new_prescription.target_reps - sets_reduction_max) if isinstance(new_prescription.target_reps, int) else new_prescription.target_reps,
                            load_method=new_prescription.load_method,
                            target_value=new_target,
                            rest_seconds=new_prescription.rest_seconds,
                            vl_max=new_prescription.vl_max,
                            notes=f"{new_prescription.notes} -load (non-key)"
                        )
                        
                        adapted_blocks.append(ExerciseBlock(
                            lift=lift,
                            intent=block.intent,
                            prescription=new_prescription
                        ))
                        explanations.append(f"{lift}: NON-KEY - load {load_scale:.0%}, sets -{sets_reduction_max}")
                elif readiness > params.readiness_high:
                    # Add a set or increase load
                    new_prescription = block.prescription
                    if isinstance(new_prescription.target_value, tuple):
                        low, high = new_prescription.target_value
                        new_target = (low * 1.025, high * 1.025)
                    else:
                        new_target = new_prescription.target_value * 1.025
                    
                    new_prescription = SetPrescription(
                        set_number=new_prescription.set_number,
                        target_reps=new_prescription.target_reps,
                        load_method=new_prescription.load_method,
                        target_value=new_target,
                        rest_seconds=new_prescription.rest_seconds,
                        vl_max=new_prescription.vl_max,
                        notes=f"{new_prescription.notes} +load"
                    )
                    
                    adapted_blocks.append(ExerciseBlock(
                        lift=lift,
                        intent=block.intent,
                        prescription=new_prescription
                    ))
                    explanations.append(f"{lift}: readiness high ({readiness:.2f}) → load +2.5%")
                else:
                    adapted_blocks.append(block)
        
        adapted_workout = StrengthWorkout(
            blocks=adapted_blocks,
            notes=explanations
        )
        
        return WorkoutPlan(
            date=plan.date,
            mode=plan.mode,
            workout=adapted_workout,
            explanations=explanations
        )
    
    elif plan.mode == "endurance":
        # Priority-aware endurance cascade
        original_zone = plan.workout.intent
        new_zone = original_zone
        
        # Determine cascade based on priority and key status
        if is_key_session:
            # Key endurance: HIIT → reduced HIIT, NOT removed unless extremely low readiness
            if day_state.readiness_endurance < 0.30:  # Extremely low
                new_zone = "z2"
                explanations.append(f"Endurance KEY: {original_zone} → {new_zone} (readiness extremely low {day_state.readiness_endurance:.2f})")
            elif original_zone == "hiit" and day_state.readiness_endurance < params.readiness_low:
                new_zone = "tempo"  # Reduced, not removed
                explanations.append(f"Endurance KEY: HIIT → {new_zone} (readiness low but protected)")
            elif day_state.E_fat > 0.5:
                new_zone = "tempo"  # Reduced from HIIT
                explanations.append(f"Endurance KEY: {original_zone} → {new_zone} (fatigue high)")
        else:
            # Non-key: standard cascade HIIT → tempo → Z2
            if day_state.readiness_endurance < params.readiness_low:
                new_zone = "z2"
            elif day_state.E_fat > 0.4 and original_zone == "hiit":
                new_zone = "tempo"
            elif day_state.E_fat > 0.5:
                new_zone = "z2"
            
            if new_zone != original_zone:
                explanations.append(f"Endurance: {original_zone} → {new_zone} (non-key, E_fat {day_state.E_fat:.2f})")
        
        if new_zone != original_zone or is_key_session:
            # Adjust duration
            if new_zone == "z2":
                if is_key_session:
                    new_duration = max(45, plan.workout.duration_min * 0.8)  # Keep some duration
                else:
                    new_duration = 30 if day_state.readiness_endurance < params.readiness_low else plan.workout.duration_min
            else:
                new_duration = plan.workout.duration_min
            
            adapted_workout = EnduranceWorkout(
                sport=plan.workout.sport,
                intent=new_zone,
                duration_min=int(new_duration),
                structure=plan.workout.structure,
                targets={"rpe": params.endurance_zones[new_zone]["rpe"]},
                notes=explanations
            )
            
            return WorkoutPlan(
                date=plan.date,
                mode=plan.mode,
                workout=adapted_workout,
                explanations=explanations
            )
        
        return plan
    
    else:  # concurrent
        # Adapt both components with priority awareness
        # In V1: simplified - just note if changes needed
        return plan


def next_set_adjustment(
    current_block: ExerciseBlock,
    last_set_velocities: List[float],
    rep_engine_summary: Dict,
    day_state: DayStateSnapshot
) -> NextSetAdjustment:
    """
    Determine intra-session adjustment for next set.
    
    Args:
        current_block: Current exercise block
        last_set_velocities: Velocities from last completed set
        rep_engine_summary: Summary from rep_engine (VL, limiting factor)
        day_state: Current day state
    
    Returns:
        NextSetAdjustment with updated prescription and action
    """
    params = CoachParams()
    
    # Extract summary data
    vl_current = rep_engine_summary.get("vl_current", 0.0)
    limiting_factor = rep_engine_summary.get("limiting", "local")
    
    # Decision logic
    if vl_current > params.vl_max_stop:
        # Stop set, reduce load significantly
        new_target = current_block.prescription.target_value
        if isinstance(new_target, tuple):
            new_target = (new_target[0] * 0.95, new_target[1] * 0.95)
        else:
            new_target = new_target * 0.95
        
        new_prescription = SetPrescription(
            set_number=current_block.prescription.set_number + 1,
            target_reps=current_block.prescription.target_reps,
            load_method=current_block.prescription.load_method,
            target_value=new_target,
            rest_seconds=current_block.prescription.rest_seconds + 60,
            vl_max=current_block.prescription.vl_max,
            notes=f"{current_block.prescription.notes} - reduced after high VL"
        )
        
        return NextSetAdjustment(
            updated_block=ExerciseBlock(
                lift=current_block.lift,
                intent=current_block.intent,
                prescription=new_prescription
            ),
            action=ActionType.STOP_SET,
            explanation=f"VL {vl_current:.1%} > {params.vl_max_stop:.1%}, load -5%, rest +60s",
            stop_current_set=True
        )
    
    elif limiting_factor == "central":
        # Central fatigue - increase rest or end heavy compounds
        new_prescription = SetPrescription(
            set_number=current_block.prescription.set_number + 1,
            target_reps=current_block.prescription.target_reps,
            load_method=current_block.prescription.load_method,
            target_value=current_block.prescription.target_value,
            rest_seconds=current_block.prescription.rest_seconds + 90,
            vl_max=current_block.prescription.vl_max,
            notes=f"{current_block.prescription.notes} - extended rest for CNS"
        )
        
        return NextSetAdjustment(
            updated_block=ExerciseBlock(
                lift=current_block.lift,
                intent=current_block.intent,
                prescription=new_prescription
            ),
            action=ActionType.EXTEND_REST,
            explanation=f"Central fatigue limiting → rest +90s"
        )
    
    elif limiting_factor == "metabolic":
        # Metabolic - reduce reps density
        new_reps = current_block.prescription.target_reps
        if isinstance(new_reps, tuple):
            new_reps = (max(1, new_reps[0] - 1), max(1, new_reps[1] - 1))
        elif isinstance(new_reps, int):
            new_reps = max(1, new_reps - 1)
        
        new_prescription = SetPrescription(
            set_number=current_block.prescription.set_number + 1,
            target_reps=new_reps,
            load_method=current_block.prescription.load_method,
            target_value=current_block.prescription.target_value,
            rest_seconds=current_block.prescription.rest_seconds + 60,
            vl_max=current_block.prescription.vl_max,
            notes=f"{current_block.prescription.notes} - reduced reps for metabolic"
        )
        
        return NextSetAdjustment(
            updated_block=ExerciseBlock(
                lift=current_block.lift,
                intent=current_block.intent,
                prescription=new_prescription
            ),
            action=ActionType.DROP_SET,
            explanation=f"Metabolic limitation → reps -1, rest +60s"
        )
    
    # Default: proceed
    return NextSetAdjustment(
        updated_block=current_block,
        action=ActionType.PROCEED,
        explanation=f"On track (VL {vl_current:.1%}, limiting: {limiting_factor})"
    )
