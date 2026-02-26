"""
Program Engine for periodization and microcycle planning.

Manages multi-week training programs that compose rep_engine, day_engine, and coach_engine
to create cohesive, progressive training plans.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
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
    priority_ratio: Optional[float] = None  # Fine-tuning ratio (default: None)
    
    # Frequency
    days_per_week_strength: int = 3
    days_per_week_endurance: int = 3
    
    @property
    def effective_priority(self) -> Priority:
        """Return effective priority based on mode."""
        if self.mode == ProgramMode.STRENGTH:
            return Priority.STRENGTH
        elif self.mode == ProgramMode.ENDURANCE:
            return Priority.ENDURANCE
        else:
            return self.priority
    
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
    
    # Sprint 5: Priority-aware fields
    key_session: bool = False  # Is this a key session that must be protected?
    session_domain: str = "rest"  # "strength", "endurance", "concurrent", "rest"
    avoid_hiit: bool = False  # HIIT should be avoided on this day
    avoid_heavy_legs: bool = False  # Heavy leg work should be avoided
    must_include_lifts: List[str] = field(default_factory=list)  # Required lifts
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "day_index": self.day_index,
            "mode": self.mode,
            "priority": self.priority,
            "time_budget_min": self.time_budget_min,
            "primary_lifts": self.primary_lifts,
            "endurance_zone": self.endurance_zone,
            "notes": self.notes,
            "key_session": self.key_session,
            "session_domain": self.session_domain,
            "avoid_hiit": self.avoid_hiit,
            "avoid_heavy_legs": self.avoid_heavy_legs,
            "must_include_lifts": self.must_include_lifts,
        }


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
            "days": [d.to_dict() for d in self.days],
            "progression": {
                "target_sets_per_week": self.progression.target_sets_per_week,
                "target_avg_intensity": self.progression.target_avg_intensity,
                "target_minutes_z2": self.progression.target_minutes_z2,
                "target_hiit_sessions": self.progression.target_hiit_sessions,
                "volume_progression": self.progression.volume_progression
            }
        }
    
    def get_key_sessions(self) -> List[DayTemplate]:
        """Return all key sessions in this microcycle."""
        return [d for d in self.days if d.key_session]
    
    def count_sessions_by_domain(self) -> Dict[str, int]:
        """Count sessions by domain."""
        counts = {"strength": 0, "endurance": 0, "concurrent": 0, "rest": 0}
        for d in self.days:
            if d.session_domain in counts:
                counts[d.session_domain] += 1
        return counts


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
    
    # Sprint 5: Priority-aware derived targets (computed from config)
    weekly_strength_sessions_target: int = field(default=0)
    weekly_endurance_sessions_target: int = field(default=0)
    weekly_hiit_cap: int = field(default=2)
    weekly_heavy_legs_cap: int = field(default=3)
    key_strength_sessions: int = field(default=1)
    key_endurance_sessions: int = field(default=1)
    
    def __post_init__(self):
        """Compute derived targets based on priority."""
        if self.weekly_strength_sessions_target == 0:
            self._compute_priority_targets()
    
    def _compute_priority_targets(self):
        """Compute weekly targets based on program priority."""
        priority = self.config.effective_priority
        mode = self.config.mode
        
        if mode == ProgramMode.STRENGTH:
            self.weekly_strength_sessions_target = self.config.days_per_week_strength
            self.weekly_endurance_sessions_target = 0
            self.weekly_hiit_cap = 0
            self.weekly_heavy_legs_cap = 3
            self.key_strength_sessions = 2
            self.key_endurance_sessions = 0
        elif mode == ProgramMode.ENDURANCE:
            self.weekly_strength_sessions_target = 0
            self.weekly_endurance_sessions_target = self.config.days_per_week_endurance
            self.weekly_hiit_cap = 2
            self.weekly_heavy_legs_cap = 1  # Limit strength maintenance
            self.key_strength_sessions = 0
            self.key_endurance_sessions = 2
        elif priority == Priority.STRENGTH:
            # Strength priority concurrent
            self.weekly_strength_sessions_target = max(3, self.config.days_per_week_strength)
            self.weekly_endurance_sessions_target = min(3, self.config.days_per_week_endurance)
            self.weekly_hiit_cap = 1
            self.weekly_heavy_legs_cap = 3
            self.key_strength_sessions = 2
            self.key_endurance_sessions = 1
        elif priority == Priority.ENDURANCE:
            # Endurance priority concurrent
            self.weekly_strength_sessions_target = min(2, self.config.days_per_week_strength)
            self.weekly_endurance_sessions_target = max(4, self.config.days_per_week_endurance)
            self.weekly_hiit_cap = 2
            self.weekly_heavy_legs_cap = 2  # Limit heavy lower
            self.key_strength_sessions = 1
            self.key_endurance_sessions = 2
        else:  # BALANCED
            self.weekly_strength_sessions_target = self.config.days_per_week_strength
            self.weekly_endurance_sessions_target = self.config.days_per_week_endurance
            self.weekly_hiit_cap = 1
            self.weekly_heavy_legs_cap = 3
            self.key_strength_sessions = 1
            self.key_endurance_sessions = 1
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "athlete_id": self.athlete_id,
            "config": {
                "mode": self.config.mode.value,
                "priority": self.config.priority.value,
                "priority_ratio": self.config.priority_ratio,
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
            # Sprint 5: Priority-aware targets
            "weekly_strength_sessions_target": self.weekly_strength_sessions_target,
            "weekly_endurance_sessions_target": self.weekly_endurance_sessions_target,
            "weekly_hiit_cap": self.weekly_hiit_cap,
            "weekly_heavy_legs_cap": self.weekly_heavy_legs_cap,
            "key_strength_sessions": self.key_strength_sessions,
            "key_endurance_sessions": self.key_endurance_sessions,
        }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "ProgramState":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        config = ProgramConfig(
            mode=ProgramMode(data["config"]["mode"]),
            priority=Priority(data["config"]["priority"]),
            priority_ratio=data["config"].get("priority_ratio"),
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
            # Sprint 5: Restore priority-aware targets
            weekly_strength_sessions_target=data.get("weekly_strength_sessions_target", 0),
            weekly_endurance_sessions_target=data.get("weekly_endurance_sessions_target", 0),
            weekly_hiit_cap=data.get("weekly_hiit_cap", 2),
            weekly_heavy_legs_cap=data.get("weekly_heavy_legs_cap", 3),
            key_strength_sessions=data.get("key_strength_sessions", 1),
            key_endurance_sessions=data.get("key_endurance_sessions", 1),
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


def _has_heavy_legs(lifts: List[str]) -> bool:
    """Check if lifts include heavy leg work."""
    heavy_legs = {"squat", "deadlift", "front squat", "romanian deadlift"}
    return any(l.lower() in heavy_legs for l in lifts)


def _is_hiit_session(zone: Optional[str]) -> bool:
    """Check if endurance zone is HIIT."""
    return zone == "hiit" if zone else False


def _mark_guardrails(days: List[DayTemplate]) -> None:
    """Mark guardrails for key sessions and interference."""
    # Find key strength lower days and mark adjacent days
    for i, day in enumerate(days):
        if day.key_session and day.session_domain in ["strength", "concurrent"]:
            if _has_heavy_legs(day.must_include_lifts or day.primary_lifts):
                # Mark adjacent days to avoid HIIT
                if i > 0:
                    days[i-1].avoid_hiit = True
                if i < len(days) - 1:
                    days[i+1].avoid_hiit = True
        
        # Mark HIIT days to avoid heavy legs
        if day.session_domain in ["endurance", "concurrent"] and _is_hiit_session(day.endurance_zone):
            day.avoid_heavy_legs = True


def create_microcycle_template(
    config: ProgramConfig,
    block_type: BlockType,
    week_index: int,
    start_date: date
) -> MicrocyclePlan:
    """
    Create a 7-day microcycle template based on program config with priority awareness.
    
    Args:
        config: Program configuration
        block_type: Current training block type
        week_index: Week within block (0-3)
        start_date: Start date of microcycle
    
    Returns:
        MicrocyclePlan
    """
    # Compute priority-aware targets
    priority = config.effective_priority
    
    # Determine session counts based on priority
    if config.mode == ProgramMode.STRENGTH:
        strength_target = config.days_per_week_strength
        endurance_target = 0
        strength_key_count = 2
        endurance_key_count = 0
    elif config.mode == ProgramMode.ENDURANCE:
        strength_target = 0
        endurance_target = config.days_per_week_endurance
        strength_key_count = 0
        endurance_key_count = 2
    elif priority == Priority.STRENGTH:
        strength_target = max(3, config.days_per_week_strength)
        endurance_target = min(3, config.days_per_week_endurance)
        strength_key_count = 2
        endurance_key_count = 1
    elif priority == Priority.ENDURANCE:
        strength_target = min(2, config.days_per_week_strength)
        endurance_target = max(4, config.days_per_week_endurance)
        strength_key_count = 1
        endurance_key_count = 2
    else:  # BALANCED
        strength_target = config.days_per_week_strength
        endurance_target = config.days_per_week_endurance
        strength_key_count = 1
        endurance_key_count = 1
    
    # Determine long session day (weekend)
    if config.long_session_day_preference == "sat":
        long_day = 5
    elif config.long_session_day_preference == "sun":
        long_day = 6
    else:
        long_day = 5 if priority == Priority.STRENGTH else 6
    
    # Distribute training days
    if config.mode == ProgramMode.STRENGTH:
        strength_days = distribute_training_days(strength_target, "strength", long_day)
        endurance_days = []
    elif config.mode == ProgramMode.ENDURANCE:
        strength_days = []
        endurance_days = distribute_training_days(endurance_target, "endurance", long_day)
    else:  # CONCURRENT
        strength_days = distribute_training_days(strength_target, "strength", long_day)
        # Endurance on remaining days, with some overlap protection
        avoid_count = 1 if priority == Priority.STRENGTH else (2 if priority == Priority.BALANCED else 0)
        endurance_days = distribute_training_days(
            endurance_target, "endurance", long_day,
            avoid_days=strength_days[:avoid_count]
        )
    
    # Build daily templates with priority-aware key session marking
    days: List[DayTemplate] = []
    strength_key_assigned = 0
    endurance_key_assigned = 0
    
    for day_idx in range(7):
        is_long = day_idx == long_day
        
        if day_idx in strength_days and day_idx in endurance_days:
            # Concurrent day
            is_key = False
            domain = "concurrent"
            
            # Determine if this should be a key session
            if priority == Priority.STRENGTH and strength_key_assigned < strength_key_count:
                is_key = True
                strength_key_assigned += 1
                domain = "strength"
            elif priority == Priority.ENDURANCE and endurance_key_assigned < endurance_key_count:
                is_key = True
                endurance_key_assigned += 1
                domain = "endurance"
            elif priority == Priority.BALANCED:
                # Balanced: first concurrent day is key for whichever needs it
                if strength_key_assigned < strength_key_count and endurance_key_assigned < endurance_key_count:
                    is_key = True
                    strength_key_assigned += 1
                    endurance_key_assigned += 1
            
            # Zone selection with priority awareness
            if block_type == BlockType.DELOAD:
                zone = "z2"
            elif priority == Priority.ENDURANCE and endurance_key_assigned <= endurance_key_count:
                zone = "hiit" if week_index >= 1 else "tempo"
            elif priority == Priority.STRENGTH:
                zone = "z2"  # Minimize interference
            else:
                zone = "tempo" if week_index >= 1 else "z2"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="concurrent",
                priority=priority.value if config.mode == ProgramMode.CONCURRENT else None,
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=config.primary_lifts[:2] if config.mode != ProgramMode.ENDURANCE else [],
                endurance_zone=zone,
                notes="Concurrent training day",
                key_session=is_key,
                session_domain=domain,
                must_include_lifts=config.primary_lifts[:1] if is_key and domain == "strength" else []
            ))
            
        elif day_idx in strength_days:
            # Strength only
            is_key = strength_key_assigned < strength_key_count
            if is_key:
                strength_key_assigned += 1
            
            if block_type == BlockType.DELOAD:
                lifts = config.primary_lifts[:2]
                intent = "technique"
            elif block_type == BlockType.PEAK:
                lifts = config.primary_lifts[:3] if is_key else config.primary_lifts[:2]
                intent = "strength"
            else:
                lifts = config.primary_lifts[:2] if is_key else [config.primary_lifts[0]]
                intent = "volume" if block_type == BlockType.BASE else "strength"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="strength",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=lifts,
                notes=f"{block_type.value} block - {intent} focus",
                key_session=is_key,
                session_domain="strength",
                must_include_lifts=lifts if is_key else []
            ))
            
        elif day_idx in endurance_days:
            # Endurance only
            is_key = endurance_key_assigned < endurance_key_count
            if is_key:
                endurance_key_assigned += 1
            
            if block_type == BlockType.BASE:
                zone = "z2"
            elif block_type == BlockType.BUILD:
                zone = "tempo" if week_index >= 1 else "z2"
            elif block_type == BlockType.PEAK:
                zone = "hiit" if (is_key and week_index == 0) else "tempo"
            else:  # DELOAD
                zone = "z2"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="endurance",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                endurance_zone=zone,
                notes=f"{block_type.value} block - {zone} focus",
                key_session=is_key,
                session_domain="endurance"
            ))
            
        else:
            # Rest day
            days.append(DayTemplate(
                day_index=day_idx,
                mode="rest",
                time_budget_min=0,
                notes="Rest and recovery",
                key_session=False,
                session_domain="rest"
            ))
    
    # Apply guardrails: mark adjacent days for key strength lower and HIIT avoidance
    _mark_guardrails(days)
    
    # Set progression targets based on block and priority
    if block_type == BlockType.BASE:
        if priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=18,
                target_avg_intensity=0.75,
                target_minutes_z2=90,
                target_hiit_sessions=0,
                volume_progression=1.05
            )
        elif priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=8,
                target_avg_intensity=0.70,
                target_minutes_z2=180,
                target_hiit_sessions=1,
                volume_progression=1.08
            )
        else:  # BALANCED
            progression = ProgressionTargets(
                target_sets_per_week=15,
                target_avg_intensity=0.75,
                target_minutes_z2=150,
                target_hiit_sessions=0,
                volume_progression=1.05
            )
    elif block_type == BlockType.BUILD:
        if priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=15,
                target_avg_intensity=0.82,
                target_minutes_z2=90,
                target_hiit_sessions=1,
                volume_progression=1.02
            )
        elif priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=8,
                target_avg_intensity=0.72,
                target_minutes_z2=150,
                target_hiit_sessions=2,
                volume_progression=1.05
            )
        else:
            progression = ProgressionTargets(
                target_sets_per_week=12,
                target_avg_intensity=0.82,
                target_minutes_z2=120,
                target_hiit_sessions=1,
                volume_progression=1.02
            )
    elif block_type == BlockType.PEAK:
        if priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=9,
                target_avg_intensity=0.88,
                target_minutes_z2=60,
                target_hiit_sessions=0,
                volume_progression=0.95
            )
        elif priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=6,
                target_avg_intensity=0.75,
                target_minutes_z2=90,
                target_hiit_sessions=2,
                volume_progression=0.95
            )
        else:
            progression = ProgressionTargets(
                target_sets_per_week=9,
                target_avg_intensity=0.88,
                target_minutes_z2=60,
                target_hiit_sessions=1,
                volume_progression=0.95
            )
    else:  # DELOAD
        deload_factor = 0.70 if priority == Priority.STRENGTH else (0.60 if priority == Priority.ENDURANCE else 0.70)
        progression = ProgressionTargets(
            target_sets_per_week=int(6 * deload_factor),
            target_avg_intensity=0.70 if priority != Priority.ENDURANCE else 0.65,
            target_minutes_z2=int(90 * deload_factor),
            target_hiit_sessions=0,
            volume_progression=deload_factor
        )
    
    # Adjust guardrails based on priority
    if priority == Priority.STRENGTH:
        guardrails = FatigueGuardrails(
            max_hiit_per_week=1,
            max_heavy_legs_sessions_per_week=3,
            max_weekly_ramp_percent=0.10,
            min_readiness_for_heavy=0.65
        )
    elif priority == Priority.ENDURANCE:
        guardrails = FatigueGuardrails(
            max_hiit_per_week=3,
            max_heavy_legs_sessions_per_week=2,
            max_weekly_ramp_percent=0.15,
            min_readiness_for_heavy=0.70
        )
    else:
        guardrails = FatigueGuardrails()
    
    return MicrocyclePlan(
        start_date=start_date,
        end_date=start_date + timedelta(days=6),
        block_type=block_type,
        week_index=week_index,
        days=days,
        progression=progression,
        guardrails=guardrails
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


# ============================================================================
# Sprint 5: Replanning Logic
# ============================================================================

@dataclass
class ReplanResult:
    """Result of replanning operation."""
    updated_microcycle: MicrocyclePlan
    moved_sessions: List[Tuple[int, int]]  # (from_day, to_day) tuples
    dropped_sessions: List[int]  # Day indices of dropped sessions
    explanation: str


def replan_missed_sessions(
    microcycle: MicrocyclePlan,
    missed_days: List[int],
    current_day: int
) -> ReplanResult:
    """
    Replan missed sessions by moving key sessions or dropping non-key ones.
    
    Strategy:
    - Key sessions: Move to next valid day within 3 days, maintain guardrails
    - Non-key sessions: Discard
    - Never stack heavy lower + HIIT
    
    Args:
        microcycle: Current microcycle plan
        missed_days: List of missed day indices (0-6)
        current_day: Current day index (can't reschedule before this)
    
    Returns:
        ReplanResult with updated microcycle and changes log
    """
    moved_sessions: List[Tuple[int, int]] = []
    dropped_sessions: List[int] = []
    explanations: List[str] = []
    
    # Sort missed days to process in order
    for missed_day in sorted(missed_days):
        if missed_day < current_day:
            continue  # Can't reschedule past days
        
        missed_template = microcycle.days[missed_day]
        
        if missed_template.mode == "rest":
            continue  # Skip rest days
        
        if not missed_template.key_session:
            # Non-key session: discard
            dropped_sessions.append(missed_day)
            explanations.append(f"Day {missed_day}: Non-key {missed_template.mode} session dropped")
            continue
        
        # Key session: try to find next valid day
        target_day = None
        for offset in range(1, 4):  # Within 3 days
            candidate = missed_day + offset
            if candidate >= 7:
                break
            if candidate < current_day:
                continue
            
            candidate_day = microcycle.days[candidate]
            
            # Check guardrails based on session type
            if missed_template.session_domain == "strength":
                # Check if heavy legs session
                if _has_heavy_legs(missed_template.must_include_lifts or missed_template.primary_lifts):
                    # Can't move to day with HIIT
                    if _is_hiit_session(candidate_day.endurance_zone):
                        continue
                    if candidate_day.avoid_hiit:
                        continue
            
            elif missed_template.session_domain == "endurance":
                # Check if HIIT session
                if _is_hiit_session(missed_template.endurance_zone):
                    # Can't move to day with heavy legs
                    if _has_heavy_legs(candidate_day.must_include_lifts or candidate_day.primary_lifts):
                        continue
                    if candidate_day.avoid_heavy_legs:
                        continue
            
            # Valid target found
            target_day = candidate
            break
        
        if target_day is not None:
            # Move session to target day
            microcycle.days[target_day] = DayTemplate(
                day_index=target_day,
                mode=missed_template.mode,
                priority=missed_template.priority,
                time_budget_min=missed_template.time_budget_min,
                primary_lifts=missed_template.primary_lifts,
                endurance_zone=missed_template.endurance_zone,
                notes=f"Rescheduled from day {missed_day}: {missed_template.notes}",
                key_session=True,  # Still a key session
                session_domain=missed_template.session_domain,
                must_include_lifts=missed_template.must_include_lifts
            )
            
            # Clear original day
            microcycle.days[missed_day] = DayTemplate(
                day_index=missed_day,
                mode="rest",
                time_budget_min=0,
                notes="Session rescheduled",
                key_session=False,
                session_domain="rest"
            )
            
            moved_sessions.append((missed_day, target_day))
            explanations.append(f"Day {missed_day}: Key {missed_template.mode} session moved to day {target_day}")
        else:
            # Could not find valid target - drop it with note
            dropped_sessions.append(missed_day)
            explanations.append(f"Day {missed_day}: Key {missed_template.mode} session dropped (no valid slot)")
    
    return ReplanResult(
        updated_microcycle=microcycle,
        moved_sessions=moved_sessions,
        dropped_sessions=dropped_sessions,
        explanation="; ".join(explanations)
    )
