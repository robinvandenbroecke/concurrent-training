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
    
    # Priority-aware fields (Sprint 5)
    key_session: bool = False  # Is this a key session that should be preserved?
    session_domain: str = "rest"  # "strength", "endurance", "concurrent", "rest"
    avoid_hiit: bool = False  # HIIT forbidden on/near this day
    avoid_heavy_legs: bool = False  # Heavy lower body forbidden
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
    
    # Priority-aware fields (Sprint 5)
    key_session: bool = False  # Is this a key session that must be protected?
    session_domain: str = "rest"  # "strength", "endurance", "concurrent", "rest"
    avoid_hiit: bool = False  # HIIT should be avoided on this day
    avoid_heavy_legs: bool = False  # Heavy leg work should be avoided
    must_include_lifts: List[str] = field(default_factory=list)  # Required lifts


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
                    "notes": d.notes,
                    "key_session": d.key_session,
                    "session_domain": d.session_domain,
                    "avoid_hiit": d.avoid_hiit,
                    "avoid_heavy_legs": d.avoid_heavy_legs,
                    "must_include_lifts": d.must_include_lifts,
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
    
    # Priority-aware weekly targets (Sprint 5)
    weekly_strength_sessions_target: int = 3
    weekly_endurance_sessions_target: int = 3
    weekly_hiit_cap: int = 1
    weekly_heavy_legs_cap: int = 2
    key_strength_sessions: int = 1
    key_endurance_sessions: int = 1
    
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
            # Priority-aware weekly targets (Sprint 5)
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
            # Priority-aware weekly targets (Sprint 5)
            weekly_strength_sessions_target=data.get("weekly_strength_sessions_target", 3),
            weekly_endurance_sessions_target=data.get("weekly_endurance_sessions_target", 3),
            weekly_hiit_cap=data.get("weekly_hiit_cap", 1),
            weekly_heavy_legs_cap=data.get("weekly_heavy_legs_cap", 2),
            key_strength_sessions=data.get("key_strength_sessions", 1),
            key_endurance_sessions=data.get("key_endurance_sessions", 1),
        )


def get_priority_weekly_targets(priority: Priority) -> Dict:
    """
    Get weekly training targets based on priority.
    
    Returns dict with:
    - strength_sessions
    - endurance_sessions
    - hiit_cap
    - heavy_legs_cap
    - key_strength_sessions
    - key_endurance_sessions
    """
    targets = {
        Priority.STRENGTH: {
            "strength_sessions": 4,
            "endurance_sessions": 2,
            "hiit_cap": 1,
            "heavy_legs_cap": 3,
            "key_strength_sessions": 2,
            "key_endurance_sessions": 1,
        },
        Priority.ENDURANCE: {
            "strength_sessions": 2,
            "endurance_sessions": 5,
            "hiit_cap": 2,
            "heavy_legs_cap": 1,
            "key_strength_sessions": 1,
            "key_endurance_sessions": 2,
        },
        Priority.BALANCED: {
            "strength_sessions": 3,
            "endurance_sessions": 3,
            "hiit_cap": 1,
            "heavy_legs_cap": 2,
            "key_strength_sessions": 1,
            "key_endurance_sessions": 1,
        },
    }
    return targets.get(priority, targets[Priority.BALANCED])


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


def _is_heavy_lower_day(lifts: List[str]) -> bool:
    """Check if any lift is a heavy lower body movement."""
    heavy_lower = {"squat", "deadlift", "front_squat", "romanian_deadlift"}
    return any(l.lower() in heavy_lower for l in lifts)


def _apply_priority_guardrails(
    days: List[DayTemplate],
    priority: Priority,
    strength_days: List[int],
    endurance_days: List[int],
    long_day: int
) -> List[DayTemplate]:
    """
    Apply priority-aware guardrails to day templates.
    
    - Key strength sessions: protected, no HIIT ±1 day
    - Key endurance sessions: protected
    - Avoid heavy legs + HIIT on same day
    """
    # Identify heavy lower body days
    heavy_lower_days = set()
    for day in days:
        if day.mode in ("strength", "concurrent") and _is_heavy_lower_day(day.primary_lifts):
            heavy_lower_days.add(day.day_index)
    
    # Identify HIIT days
    hiit_days = set()
    for day in days:
        if day.endurance_zone == "hiit":
            hiit_days.add(day.day_index)
    
    # Apply guardrails
    for day in days:
        if day.mode == "rest":
            continue
        
        # Set session domain
        if day.mode == "strength":
            day.session_domain = "strength"
        elif day.mode == "endurance":
            day.session_domain = "endurance"
        elif day.mode == "concurrent":
            day.session_domain = "concurrent"
        
        # Set avoid flags based on neighbors
        day_before = (day.day_index - 1) % 7
        day_after = (day.day_index + 1) % 7
        
        # Key session marking based on priority
        if priority == Priority.STRENGTH:
            # Heavy lower body sessions are key
            if day.mode in ("strength", "concurrent") and _is_heavy_lower_day(day.primary_lifts):
                day.key_session = True
                day.avoid_hiit = True  # No HIIT near heavy lower
            # First strength session of week is key
            elif day.mode == "strength" and day.day_index in strength_days[:1]:
                day.key_session = True
        
        elif priority == Priority.ENDURANCE:
            # Long endurance day is key
            if day.day_index == long_day and day.mode in ("endurance", "concurrent"):
                day.key_session = True
            # HIIT sessions are key (limited resource)
            elif day.endurance_zone == "hiit":
                day.key_session = True
            # Keep strength maintenance minimal
            if day.mode == "strength":
                day.avoid_heavy_legs = True
                day.must_include_lifts = ["bench", "press"][:1]  # Upper only
        
        else:  # BALANCED
            # One key strength, one key endurance
            if day.mode == "strength" and day.day_index == strength_days[0] if strength_days else False:
                day.key_session = True
            if day.mode in ("endurance", "concurrent") and day.day_index == long_day:
                day.key_session = True
        
        # Universal: avoid HIIT on heavy lower day
        if _is_heavy_lower_day(day.primary_lifts):
            day.avoid_hiit = True
            if day_after in hiit_days or day_before in hiit_days:
                # Mark neighboring days to avoid HIIT
                pass  # Already marked via day.avoid_hiit
        
        # Universal: avoid heavy legs near HIIT
        if day.endurance_zone == "hiit":
            day.avoid_heavy_legs = True
    
    return days


def create_microcycle_template(
    config: ProgramConfig,
    block_type: BlockType,
    week_index: int,
    start_date: date
) -> MicrocyclePlan:
    """
    Create a 7-day microcycle template based on program config.
    PRIORITY-AWARE: Structure varies by priority setting.
    
    Args:
        config: Program configuration
        block_type: Current training block type
        week_index: Week within block (0-3)
        start_date: Start date of microcycle
    
    Returns:
        MicrocyclePlan
    """
    days = []
    effective_priority = config.effective_priority
    
    # Get priority-based targets
    targets = get_priority_weekly_targets(effective_priority)
    
    # Determine long session day (weekend)
    if config.long_session_day_preference == "sat":
        long_day = 5
    elif config.long_session_day_preference == "sun":
        long_day = 6
    else:
        long_day = 5 if config.mode != ProgramMode.ENDURANCE else 6
    
    # PRIORITY-AWARE day distribution
    if config.mode == ProgramMode.STRENGTH:
        strength_days = distribute_training_days(
            targets["strength_sessions"], "strength", long_day
        )
        endurance_days = []
    elif config.mode == ProgramMode.ENDURANCE:
        strength_days = []
        endurance_days = distribute_training_days(
            targets["endurance_sessions"], "endurance", long_day
        )
    else:  # CONCURRENT - priority affects distribution
        if effective_priority == Priority.STRENGTH:
            # More strength days, endurance secondary
            strength_days = distribute_training_days(
                targets["strength_sessions"], "strength", long_day
            )
            # Endurance on remaining days, avoiding heavy lower ±1
            avoid_days = set(strength_days)
            for sd in strength_days:
                avoid_days.add((sd - 1) % 7)
                avoid_days.add((sd + 1) % 7)
            endurance_days = distribute_training_days(
                targets["endurance_sessions"], "endurance", long_day,
                avoid_days=list(avoid_days)
            )
        
        elif effective_priority == Priority.ENDURANCE:
            # More endurance days, strength maintenance only
            endurance_days = distribute_training_days(
                targets["endurance_sessions"], "endurance", long_day
            )
            # Strength on easy days, minimal
            avoid_days = set(endurance_days)
            # Avoid days with HIIT
            for ed in endurance_days:
                avoid_days.add(ed)
            strength_days = distribute_training_days(
                targets["strength_sessions"], "strength", long_day,
                avoid_days=list(avoid_days)
            )
        
        else:  # BALANCED - even distribution
            strength_days = distribute_training_days(
                targets["strength_sessions"], "strength", long_day
            )
            endurance_days = distribute_training_days(
                targets["endurance_sessions"], "endurance", long_day,
                avoid_days=strength_days[:2]
            )
    
    # Build daily templates
    for day_idx in range(7):
        if day_idx in strength_days and day_idx in endurance_days:
            # Concurrent day - rare in priority modes
            is_long = day_idx == long_day
            is_key = day_idx == long_day  # Long day is key
            days.append(DayTemplate(
                day_index=day_idx,
                mode="concurrent",
                priority=effective_priority.value,
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=config.primary_lifts[:2] if effective_priority != Priority.ENDURANCE else ["bench", "press"],
                endurance_zone="z2" if block_type == BlockType.BASE else ("tempo" if week_index < 2 else "hiit"),
                notes="Concurrent training day",
                key_session=is_key,
                session_domain="concurrent",
            ))
        
        elif day_idx in strength_days:
            # Strength only
            is_long = day_idx == long_day
            
            # Priority-aware lift selection
            if effective_priority == Priority.STRENGTH:
                if block_type == BlockType.DELOAD:
                    lifts = config.primary_lifts[:2]
                elif block_type == BlockType.PEAK:
                    lifts = config.primary_lifts[:3]  # More lifts in peak
                else:
                    lifts = config.primary_lifts[:2]
                # First strength day is heavy lower
                if day_idx == strength_days[0]:
                    lifts = ["squat"] + [l for l in lifts if l != "squat"][:2]
            
            elif effective_priority == Priority.ENDURANCE:
                # Maintenance: upper body focus, minimal lower
                lifts = ["bench", "press"][:2]
                if block_type == BlockType.PEAK:
                    lifts.append("squat")  # Keep some leg strength
            
            else:  # BALANCED
                if block_type == BlockType.DELOAD:
                    lifts = config.primary_lifts[:2]
                elif block_type == BlockType.PEAK:
                    lifts = config.primary_lifts[:3]
                else:
                    lifts = config.primary_lifts[:2]
            
            if block_type == BlockType.DELOAD:
                intent = "technique"
            elif block_type == BlockType.PEAK:
                intent = "strength"
            else:
                intent = "volume" if block_type == BlockType.BASE else "strength"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="strength",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                primary_lifts=lifts,
                notes=f"{block_type.value} block - {intent} focus",
                session_domain="strength",
            ))
        
        elif day_idx in endurance_days:
            # Endurance only
            is_long = day_idx == long_day
            
            # Priority-aware zone selection
            if effective_priority == Priority.ENDURANCE:
                # More aggressive progression
                if block_type == BlockType.BASE:
                    zone = "z2"
                elif block_type == BlockType.BUILD:
                    zone = "tempo" if week_index >= 0 else "z2"
                elif block_type == BlockType.PEAK:
                    zone = "hiit" if week_index < 2 else "tempo"
                else:
                    zone = "z2"
            
            elif effective_priority == Priority.STRENGTH:
                # Conservative, more Z2 for recovery
                if block_type == BlockType.BASE:
                    zone = "z2"
                elif block_type == BlockType.BUILD:
                    zone = "z2"  # No tempo for strength priority
                elif block_type == BlockType.PEAK:
                    zone = "tempo" if week_index == 0 else "z2"  # Minimal intensity
                else:
                    zone = "z2"
            
            else:  # BALANCED
                if block_type == BlockType.BASE:
                    zone = "z2"
                elif block_type == BlockType.BUILD:
                    zone = "tempo" if week_index >= 1 else "z2"
                elif block_type == BlockType.PEAK:
                    zone = "hiit" if week_index == 0 else "tempo"
                else:
                    zone = "z2"
            
            # Cap HIIT per priority
            if zone == "hiit":
                hiit_count = sum(1 for d in days if d.endurance_zone == "hiit")
                if hiit_count >= targets["hiit_cap"]:
                    zone = "tempo"
            
            days.append(DayTemplate(
                day_index=day_idx,
                mode="endurance",
                time_budget_min=config.time_budget_weekend_min if is_long else config.time_budget_weekday_min,
                endurance_zone=zone,
                notes=f"{block_type.value} block - {zone} focus",
                session_domain="endurance",
            ))
        
        else:
            # Rest day
            days.append(DayTemplate(
                day_index=day_idx,
                mode="rest",
                time_budget_min=0,
                notes="Rest and recovery",
                session_domain="rest",
            ))
    
    # Apply priority guardrails
    days = _apply_priority_guardrails(
        days, effective_priority, strength_days, endurance_days, long_day
    )
    
    # Set progression targets based on block AND priority
    if block_type == BlockType.BASE:
        if effective_priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=18,
                target_avg_intensity=0.78,
                target_minutes_z2=90,
                target_hiit_sessions=0,
                volume_progression=1.05
            )
        elif effective_priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=8,
                target_avg_intensity=0.70,
                target_minutes_z2=240,
                target_hiit_sessions=0,
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
        if effective_priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=15,
                target_avg_intensity=0.85,
                target_minutes_z2=80,
                target_hiit_sessions=0,
                volume_progression=1.02
            )
        elif effective_priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=6,
                target_avg_intensity=0.72,
                target_minutes_z2=180,
                target_hiit_sessions=1,
                volume_progression=1.05
            )
        else:  # BALANCED
            progression = ProgressionTargets(
                target_sets_per_week=12,
                target_avg_intensity=0.82,
                target_minutes_z2=120,
                target_hiit_sessions=1,
                volume_progression=1.02
            )
    
    elif block_type == BlockType.PEAK:
        if effective_priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=10,
                target_avg_intensity=0.90,
                target_minutes_z2=60,
                target_hiit_sessions=0,
                volume_progression=0.95
            )
        elif effective_priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=4,
                target_avg_intensity=0.75,
                target_minutes_z2=120,
                target_hiit_sessions=2,
                volume_progression=0.95
            )
        else:  # BALANCED
            progression = ProgressionTargets(
                target_sets_per_week=9,
                target_avg_intensity=0.88,
                target_minutes_z2=60,
                target_hiit_sessions=2,
                volume_progression=0.95
            )
    
    else:  # DELOAD
        if effective_priority == Priority.STRENGTH:
            progression = ProgressionTargets(
                target_sets_per_week=8,
                target_avg_intensity=0.70,
                target_minutes_z2=60,
                target_hiit_sessions=0,
                volume_progression=0.70
            )
        elif effective_priority == Priority.ENDURANCE:
            progression = ProgressionTargets(
                target_sets_per_week=3,
                target_avg_intensity=0.65,
                target_minutes_z2=120,
                target_hiit_sessions=0,
                volume_progression=0.70
            )
        else:  # BALANCED
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
    PRIORITY-AWARE: Sets weekly targets based on priority.
    
    Args:
        athlete_id: Athlete identifier
        config: Program configuration
        start_date: Program start date (default: today)
    
    Returns:
        Tuple of (ProgramState, first MicrocyclePlan)
    """
    start_date = start_date or date.today()
    
    # Get priority-based targets
    targets = get_priority_weekly_targets(config.effective_priority)
    
    # Create initial state with priority-aware targets
    state = ProgramState(
        athlete_id=athlete_id,
        config=config,
        current_block=BlockType.BASE,
        block_week_index=0,
        microcycle_index=0,
        start_date=start_date,
        current_week_start=start_date,
        # Priority-aware weekly targets (Sprint 5)
        weekly_strength_sessions_target=targets["strength_sessions"],
        weekly_endurance_sessions_target=targets["endurance_sessions"],
        weekly_hiit_cap=targets["hiit_cap"],
        weekly_heavy_legs_cap=targets["heavy_legs_cap"],
        key_strength_sessions=targets["key_strength_sessions"],
        key_endurance_sessions=targets["key_endurance_sessions"],
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
# PRIORITY-AWARE REPLANNING (Sprint 5)
# ============================================================================

def replan_missed_session(
    microcycle: MicrocyclePlan,
    missed_date: date,
    completed_dates: List[date],
    priority: Priority
) -> Optional[DayTemplate]:
    """
    Replan a missed session.
    PRIORITY-AWARE: Key sessions are moved, non-key sessions are discarded.
    
    Args:
        microcycle: Current microcycle plan
        missed_date: Date of missed session
        completed_dates: Dates of completed sessions (to avoid conflicts)
        priority: Training priority
    
    Returns:
        New DayTemplate for rescheduled session, or None if discarded
    """
    # Get the missed day template
    days_diff = (missed_date - microcycle.start_date).days
    if days_diff < 0 or days_diff >= 7:
        return None
    
    missed_day = microcycle.days[days_diff]
    
    # Non-key sessions: discard
    if not missed_day.key_session:
        return None
    
    # Key sessions: find next valid day within 3 days
    for offset in range(1, 4):  # 1-3 days forward
        new_date = missed_date + timedelta(days=offset)
        new_idx = days_diff + offset
        
        if new_idx >= 7 or new_date in completed_dates:
            continue
        
        # Check guardrails
        existing_day = microcycle.days[new_idx] if new_idx < 7 else None
        
        # If it's a rest day, use it
        if existing_day and existing_day.mode == "rest":
            # Create new template for this day
            return DayTemplate(
                day_index=new_idx,
                mode=missed_day.mode,
                priority=missed_day.priority,
                time_budget_min=missed_day.time_budget_min,
                primary_lifts=missed_day.primary_lifts,
                endurance_zone=missed_day.endurance_zone,
                notes=f"Rescheduled from {missed_date.isoformat()}",
                key_session=True,  # Still key
                session_domain=missed_day.session_domain,
                avoid_hiit=missed_day.avoid_hiit,
                avoid_heavy_legs=missed_day.avoid_heavy_legs,
                must_include_lifts=missed_day.must_include_lifts,
            )
        
        # If concurrent day and missed was strength, can combine
        if existing_day and existing_day.mode == "concurrent" and missed_day.mode == "strength":
            return DayTemplate(
                day_index=new_idx,
                mode="concurrent",
                priority=missed_day.priority,
                time_budget_min=max(missed_day.time_budget_min, existing_day.time_budget_min),
                primary_lifts=list(set(missed_day.primary_lifts + existing_day.primary_lifts)),
                endurance_zone=existing_day.endurance_zone,
                notes=f"Combined with existing + rescheduled from {missed_date.isoformat()}",
                key_session=True,
                session_domain="concurrent",
                avoid_hiit=missed_day.avoid_hiit or existing_day.avoid_hiit,
                avoid_heavy_legs=missed_day.avoid_heavy_legs or existing_day.avoid_heavy_legs,
                must_include_lifts=missed_day.must_include_lifts,
            )
    
    # Could not find valid day within 3 days - keep as missed but note it
    return None


def compress_week(
    microcycle: MicrocyclePlan,
    missed_dates: List[date],
    completed_dates: List[date],
    priority: Priority
) -> MicrocyclePlan:
    """
    Compress week after multiple missed sessions.
    PRIORITY-AWARE: Never stack heavy lower + HIIT.
    
    Args:
        microcycle: Original microcycle
        missed_dates: List of missed session dates
        completed_dates: List of completed session dates
        priority: Training priority
    
    Returns:
        Modified MicrocyclePlan
    """
    # Start with copy of days
    new_days = [DayTemplate(
        day_index=d.day_index,
        mode=d.mode,
        priority=d.priority,
        time_budget_min=d.time_budget_min,
        primary_lifts=d.primary_lifts[:],
        endurance_zone=d.endurance_zone,
        notes=d.notes,
        key_session=d.key_session,
        session_domain=d.session_domain,
        avoid_hiit=d.avoid_hiit,
        avoid_heavy_legs=d.avoid_heavy_legs,
        must_include_lifts=d.must_include_lifts[:],
    ) for d in microcycle.days]
    
    # Collect key sessions to preserve
    key_sessions = []
    for missed_date in missed_dates:
        days_diff = (missed_date - microcycle.start_date).days
        if 0 <= days_diff < 7:
            day = microcycle.days[days_diff]
            if day.key_session:
                key_sessions.append((missed_date, day))
    
    # Try to fit key sessions into remaining days
    for missed_date, missed_day in key_sessions:
        # Find first available day
        for new_day in new_days:
            if new_day.mode == "rest" and new_day.day_index not in [
                (d - microcycle.start_date).days for d in completed_dates
            ]:
                # Check guardrails: no heavy lower + HIIT
                has_heavy_lower = _is_heavy_lower_day(missed_day.primary_lifts)
                would_have_hiit = new_day.endurance_zone == "hiit" or missed_day.endurance_zone == "hiit"
                
                if has_heavy_lower and would_have_hiit:
                    # Skip this day, would violate guardrail
                    continue
                
                # Schedule here
                new_day.mode = missed_day.mode
                new_day.priority = missed_day.priority
                new_day.time_budget_min = missed_day.time_budget_min
                new_day.primary_lifts = missed_day.primary_lifts[:]
                new_day.endurance_zone = missed_day.endurance_zone
                new_day.notes = f"Compressed from {missed_date.isoformat()}"
                new_day.key_session = True
                new_day.session_domain = missed_day.session_domain
                new_day.avoid_hiit = missed_day.avoid_hiit
                new_day.avoid_heavy_legs = missed_day.avoid_heavy_legs
                new_day.must_include_lifts = missed_day.must_include_lifts[:]
                break
    
    return MicrocyclePlan(
        start_date=microcycle.start_date,
        end_date=microcycle.end_date,
        block_type=microcycle.block_type,
        week_index=microcycle.week_index,
        days=new_days,
        progression=microcycle.progression,
        guardrails=microcycle.guardrails
    )


def get_weekly_summary(microcycle: MicrocyclePlan) -> Dict:
    """
    Get summary of weekly plan.
    
    Returns dict with counts and key session info.
    """
    strength_days = [d for d in microcycle.days if d.mode == "strength"]
    endurance_days = [d for d in microcycle.days if d.mode == "endurance"]
    concurrent_days = [d for d in microcycle.days if d.mode == "concurrent"]
    key_sessions = [d for d in microcycle.days if d.key_session]
    
    return {
        "total_sessions": len(strength_days) + len(endurance_days) + len(concurrent_days),
        "strength_sessions": len(strength_days),
        "endurance_sessions": len(endurance_days),
        "concurrent_sessions": len(concurrent_days),
        "key_sessions": len(key_sessions),
        "hiit_sessions": len([d for d in microcycle.days if d.endurance_zone == "hiit"]),
        "heavy_legs_sessions": len([d for d in microcycle.days if _is_heavy_lower_day(d.primary_lifts)]),
    }
