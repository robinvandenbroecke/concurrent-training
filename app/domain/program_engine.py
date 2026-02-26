"""
Program Engine for periodization and microcycle planning.

Manages multi-week training programs that compose rep_engine, day_engine, and coach_engine
to create cohesive, progressive training plans.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import date, timedelta
import json


class ProgramMode(str, Enum):
    """Program training mode."""
    STRENGTH = "strength"
    ENDURANCE = "endurance"
    CONCURRENT = "concurrent"


class BlockType(str, Enum):
    """Training block types."""
    BASE = "base"  # Volume focus
    BUILD = "build"  # Intensity focus
    PEAK = "peak"  # Performance focus
    DELOAD = "deload"  # Recovery focus


class Priority(str, Enum):
    """Training priority for concurrent programs."""
    STRENGTH = "strength"
    ENDURANCE = "endurance"
    BALANCED = "balanced"


@dataclass
class ProgramConfig:
    """Configuration for a training program."""
    mode: ProgramMode
    priority: Priority = Priority.BALANCED
    
    # Frequency
    days_per_week_strength: int = 3
    days_per_week_endurance: int = 3
    
    # Scheduling preferences
    long_session_day_preference: str = "auto"  # "sat", "sun", "auto"
    time_budget_weekday_min: int = 45
    time_budget_weekend_min: int = 90
    
    # Capabilities
    vbt_available: bool = True
    available_sports: List[str] = field(default_factory=lambda: ["cycling", "running", "swimming"])
    primary_lifts: List[str] = field(default_factory=lambda: ["squat", "bench", "deadlift", "press", "clean"])
    
    # Constraints
    constraints: Dict = field(default_factory=dict)
    
    # Block progression
    weeks_per_block: int = 4
    include_deload: bool = True


@dataclass
class ProgressionTargets:
    """Weekly progression targets per lift or endurance."""
    # Strength
    target_sets_per_week: int = 12
    target_avg_intensity: float = 0.80  # % of C_l
    
    # Endurance
    target_minutes_z2: int = 120
    target_hiit_sessions: int = 1
    
    # Volume progression (weekly multiplier)
    volume_progression: float = 1.05  # +5% per week


@dataclass
class FatigueGuardrails:
    """Safety limits to prevent overreaching."""
    max_hiit_per_week: int = 2
    max_heavy_legs_sessions_per_week: int = 3
    max_weekly_ramp_percent: float = 0.10  # 10% volume increase max
    min_readiness_for_heavy: float = 0.65


@dataclass
class DayTemplate:
    """Template for a single day in a microcycle."""
    day_index: int  # 0-6 (Monday-Sunday)
    mode: str  # "strength", "endurance", "concurrent", "rest"
    priority: Optional[str] = None  # For concurrent days
    time_budget_min: int = 60
    primary_lifts: List[str] = field(default_factory=list)
    endurance_zone: Optional[str] = None  # "z2", "tempo", "hiit"
    notes: str = ""


@dataclass
class MicrocyclePlan:
    """7-day training microcycle."""
    start_date: date
    end_date: date
    block_type: BlockType
    week_index: int  # Week within block (0-3)
    days: List[DayTemplate] = field(default_factory=list)
    
    # Weekly targets
    progression: ProgressionTargets = field(default_factory=ProgressionTargets)
    
    # Safety
    guardrails: FatigueGuardrails = field(default_factory=FatigueGuardrails)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "block_type": self.block_type.value,
            "week_index": self.week_index,
            "days": [
                {
                    "day_index": d.day_index,
                    "mode": d.mode,
                    "priority": d.priority,
                    "time_budget_min": d.time_budget_min,
                    "primary_lifts": d.primary_lifts,
                    "endurance_zone": d.endurance_zone,
                    "notes": d.notes
                }
                for d in self.days
            ],
            "progression": {
                "target_sets_per_week": self.progression.target_sets_per_week,
                "target_avg_intensity": self.progression.target_avg_intensity,
                "target_minutes_z2": self.progression.target_minutes_z2,
                "target_hiit_sessions": self.progression.target_hiit_sessions,
                "volume_progression": self.progression.volume_progression
            }
        }


@dataclass
class ProgramState:
    """Current state of an active program."""
    athlete_id: str
    config: ProgramConfig
    
    # Block tracking
    current_block: BlockType
    block_week_index: int  # 0-3 within block
    microcycle_index: int  # Total microcycles completed
    
    # Dates
    start_date: date
    current_week_start: date
    last_deload_date: Optional[date] = None
    
    # Progression tracking
    progression_targets: Dict[str, ProgressionTargets] = field(default_factory=dict)
    
    # History (simplified)
    last_14_days_summary: Dict = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "athlete_id": self.athlete_id,
            "config": {
                "mode": self.config.mode.value,
                "priority": self.config.priority.value,
                "days_per_week_strength": self.config.days_per_week_strength,
                "days_per_week_endurance": self.config.days_per_week_endurance,
                "primary_lifts": self.config.primary_lifts,
            },
            "current_block": self.current_block.value,
            "block_week_index": self.block_week_index,
            "microcycle_index": self.microcycle_index,
            "start_date": self.start_date.isoformat(),
            "current_week_start": self.current_week_start.isoformat(),
            "last_deload_date": self.last_deload_date.isoformat() if self.last_deload_date else None,
        }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "ProgramState":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        config = ProgramConfig(
            mode=ProgramMode(data["config"]["mode"]),
            priority=Priority(data["config"]["priority"]),
            days_per_week_strength=data["config"].get("days_per_week_strength", 3),
            days_per_week_endurance=data["config"].get("days_per_week_endurance", 3),
            primary_lifts=data["config"].get("primary_lifts", ["squat", "bench", "deadlift"]),
        )
        return cls(
            athlete_id=data["athlete_id"],
            config=config,
            current_block=BlockType(data["current_block"]),
            block_week_index=data["block_week_index"],
            microcycle_index=data["microcycle_index"],
            start_date=date.fromisoformat(data["start_date"]),
            current_week_start=date.fromisoformat(data["current_week_start"]),
            last_deload_date=date.fromisoformat(data["last_deload_date"]) if data.get("last_deload_date") else None,
        )


def distribute_training_days(
    days_per_week: int,
    mode: str,
    long_day: int = 5,  # Saturday default
    avoid_days: List[int] = None
) -> List[int]:
    """
    Distribute training days across the week.
    
    Returns list of day indices (0=Monday, 6=Sunday)
    """
    avoid_days = avoid_days or []
    available_days = [d for d in range(7) if d not in avoid_days]
    
    if days_per_week >= len(available_days):
        return available_days
    
    # Strategy: space evenly, preferring non-consecutive
    selected = []
    
    # Always include one weekend day for longer session if possible
    if long_day in available_days and days_per_week >= 2:
        selected.append(long_day)
        available_days.remove(long_day)
        days_per_week -= 1
    
    # Distribute remaining days evenly
    step = len(available_days) / days_per_week
    for i in range(days_per_week):
        idx = min(int(i * step), len(available_days) - 1)
        selected.append(available_days[idx])
        available_days.pop(idx)
    
    return sorted(selected)


def create_microcycle_template(
    config: ProgramConfig,
    block_type: BlockType,
    week_index: int,
    start_date: date
) -> MicrocyclePlan:
    """
    Create a 7-day microcycle template based on program config.
    
    Args:
        config: Program configuration
        block_type: Current training block type
        week_index: Week within block (0-3)
        start_date: Start date of microcycle
    
    Returns:
        MicrocyclePlan
    """
    days = []
    
    # Determine long session day (weekend)
    if config.long_session_day_preference == "sat":
        long_day = 5  # Saturday
    elif config.long_session_day_preference == "sun":
        long_day = 6  # Sunday
    else:
        long_day = 5 if config.mode != ProgramMode.ENDURANCE else 6
    
    # Distribute strength and endurance days
    if config.mode == ProgramMode.STRENGTH:
        strength_days = distribute_training_days(
            config.days_per_week_strength, "strength", long_day
        )
        endurance_days = []
    elif config.mode == ProgramMode.ENDURANCE:
        strength_days = []
        endurance_days = distribute_training_days(
            config.days_per_week_endurance, "endurance", long_day
        )
    else:  # CONCURRENT
        # Distribute both with minimal overlap
        strength_days = distribute_training_days(
            config.days_per_week_strength, "strength", long_day
        )
        # Endurance on different days, or same if concurrent efficiency desired
        endurance_days = distribute_training_days(
            config.days_per_week_endurance, "endurance", long_day,
            avoid_days=strength_days[:2]  # Avoid at least 2 strength days
        )
    
    # Build daily templates
    for day_idx in range(7):
        if day_idx in strength_days and day_idx in endurance_days:
            # Concurrent day
            is_long = day_idx == long_day
            days.append(DayTemplate(
                day_index=day_idx,
                mode="concurrent",
                priority=config.priority.value if config.mode == ProgramMode.CONCURRENT else None,
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=config.primary_lifts[:2] if config.mode != ProgramMode.ENDURANCE else [],
                endurance_zone="z2" if block_type == BlockType.BASE else ("tempo" if week_index < 2 else "hiit"),
                notes="Concurrent training day"
            ))
        elif day_idx in strength_days:
            # Strength only
            is_long = day_idx == long_day
            if block_type == BlockType.DELOAD:
                lifts = config.primary_lifts[:2]
                intent = "technique"
            elif block_type == BlockType.PEAK:
                lifts = config.primary_lifts[:3]
                intent = "strength"
            else:
                lifts = config.primary_lifts[:2]
                intent = "volume" if block_type == BlockType.BASE else "strength"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="strength",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=lifts,
                notes=f"{block_type.value} block - {intent} focus"
            ))
        elif day_idx in endurance_days:
            # Endurance only
            is_long = day_idx == long_day
            if block_type == BlockType.BASE:
                zone = "z2"
            elif block_type == BlockType.BUILD:
                zone = "tempo" if week_index >= 1 else "z2"
            elif block_type == BlockType.PEAK:
                zone = "hiit" if week_index == 0 else "tempo"
            else:  # DELOAD
                zone = "z2"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="endurance",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                endurance_zone=zone,
                notes=f"{block_type.value} block - {zone} focus"
            ))
        else:
            # Rest day
            days.append(DayTemplate(
                day_index=day_idx,
                mode="rest",
                time_budget_min=0,
                notes="Rest and recovery"
            ))
    
    # Set progression targets based on block
    if block_type == BlockType.BASE:
        progression = ProgressionTargets(
            target_sets_per_week=15,
            target_avg_intensity=0.75,
            target_minutes_z2=150,
            target_hiit_sessions=0,
            volume_progression=1.05
        )
    elif block_type == BlockType.BUILD:
        progression = ProgressionTargets(
            target_sets_per_week=12,
            target_avg_intensity=0.82,
            target_minutes_z2=120,
            target_hiit_sessions=1,
            volume_progression=1.02
        )
    elif block_type == BlockType.PEAK:
        progression = ProgressionTargets(
            target_sets_per_week=9,
            target_avg_intensity=0.88,
            target_minutes_z2=60,
            target_hiit_sessions=2,
            volume_progression=0.95
        )
    else:  # DELOAD
        progression = ProgressionTargets(
            target_sets_per_week=6,
            target_avg_intensity=0.70,
            target_minutes_z2=90,
            target_hiit_sessions=0,
            volume_progression=0.70
        )
    
    return MicrocyclePlan(
        start_date=start_date,
        end_date=start_date + timedelta(days=6),
        block_type=block_type,
        week_index=week_index,
        days=days,
        progression=progression,
        guardrails=FatigueGuardrails()
    )


def start_program(
    athlete_id: str,
    config: ProgramConfig,
    start_date: date = None
) -> Tuple[ProgramState, MicrocyclePlan]:
    """
    Start a new training program.
    
    Args:
        athlete_id: Athlete identifier
        config: Program configuration
        start_date: Program start date (default: today)
    
    Returns:
        Tuple of (ProgramState, first MicrocyclePlan)
    """
    start_date = start_date or date.today()
    
    # Create initial state
    state = ProgramState(
        athlete_id=athlete_id,
        config=config,
        current_block=BlockType.BASE,
        block_week_index=0,
        microcycle_index=0,
        start_date=start_date,
        current_week_start=start_date
    )
    
    # Generate first microcycle
    microcycle = create_microcycle_template(
        config=config,
        block_type=BlockType.BASE,
        week_index=0,
        start_date=start_date
    )
    
    return state, microcycle


def advance_microcycle(
    state: ProgramState,
    completed_workouts: List[Dict] = None
) -> Tuple[ProgramState, MicrocyclePlan]:
    """
    Advance to next microcycle.
    
    Args:
        state: Current program state
        completed_workouts: Summary of completed workouts (optional)
    
    Returns:
        Tuple of (updated ProgramState, next MicrocyclePlan)
    """
    # Update state
    state.microcycle_index += 1
    state.block_week_index += 1
    state.current_week_start += timedelta(days=7)
    
    # Check if block should change
    if state.block_week_index >= state.config.weeks_per_block:
        state.block_week_index = 0
        
        # Block progression
        if state.current_block == BlockType.BASE:
            state.current_block = BlockType.BUILD
        elif state.current_block == BlockType.BUILD:
            state.current_block = BlockType.PEAK
        elif state.current_block == BlockType.PEAK:
            if state.config.include_deload:
                state.current_block = BlockType.DELOAD
            else:
                state.current_block = BlockType.BASE  # Reset
        elif state.current_block == BlockType.DELOAD:
            state.current_block = BlockType.BASE  # New cycle
            state.last_deload_date = state.current_week_start - timedelta(days=7)
    
    # Generate next microcycle
    microcycle = create_microcycle_template(
        config=state.config,
        block_type=state.current_block,
        week_index=state.block_week_index,
        start_date=state.current_week_start
    )
    
    return state, microcycle


def get_day_workout_spec(
    microcycle: MicrocyclePlan,
    day_date: date,
    state: ProgramState = None
) -> Optional[DayTemplate]:
    """
    Get the workout specification for a specific day.
    
    Args:
        microcycle: Current microcycle plan
        day_date: Date to get workout for
        state: Optional program state for adjustments
    
    Returns:
        DayTemplate or None if rest day
    """
    # Calculate day index within microcycle
    days_diff = (day_date - microcycle.start_date).days
    if days_diff < 0 or days_diff >= 7:
        return None
    
    day_template = microcycle.days[days_diff]
    
    if day_template.mode == "rest":
        return None
    
    return day_template


def should_deload(
    state: ProgramState,
    recent_readiness: Dict[str, float],
    sessions_last_7_days: int
) -> bool:
    """
    Determine if athlete should deload based on state and readiness.
    
    Args:
        state: Current program state
        recent_readiness: Recent readiness scores
        sessions_last_7_days: Number of sessions in last 7 days
    
    Returns:
        True if deload recommended
    """
    # Auto-deload if it's scheduled
    if state.current_block == BlockType.DELOAD:
        return True
    
    # Check if overdue for deload
    if state.last_deload_date:
        weeks_since_deload = (state.current_week_start - state.last_deload_date).days / 7
        if weeks_since_deload >= 4:
            return True
    
    # Check readiness indicators
    avg_readiness = sum(recent_readiness.values()) / len(recent_readiness) if recent_readiness else 1.0
    if avg_readiness < 0.50 and state.current_block != BlockType.DELOAD:
        return True
    
    # Check volume indicators
    if sessions_last_7_days > 8 and state.current_block != BlockType.DELOAD:
        return True
    
    return False
