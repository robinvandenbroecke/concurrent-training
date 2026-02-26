"""
Goal Engine for event-driven periodization and macrocycle planning.

Manages goal setting, phase scheduling, and macrocycle context to guide
program_engine toward peak performance for specific target events.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import date, timedelta
import json


class GoalType(str, Enum):
    """Types of training goals."""
    STRENGTH_PEAK = "strength_peak"  # Peak for 1RM/3RM test
    ENDURANCE_EVENT = "endurance_event"  # Race/time trial
    CONCURRENT_EVENT = "concurrent_event"  # Hybrid goal


class ConcurrentTarget(str, Enum):
    """Concurrent training target profiles."""
    STRONG_AND_DURABLE = "strong_and_durable"  # Maintain strength, build endurance
    POWER_ENDURANCE = "power_endurance"  # Explosive endurance focus
    GENERAL_FITNESS = "general_fitness"  # Balanced maintenance


class PhaseType(str, Enum):
    """Training phases in a macrocycle."""
    BASE = "base"  # Volume focus, build foundation
    BUILD = "build"  # Intensity focus, build specific fitness
    PEAK = "peak"  # Maximal efforts, minimal volume
    TAPER = "taper"  # Reduce fatigue, maintain sharpness


@dataclass
class StrengthTarget:
    """Target for a specific lift."""
    lift: str
    metric: str  # "1rm" or "3rm"
    target_value: Optional[float] = None  # Optional specific target weight
    
    def to_dict(self) -> dict:
        return {
            "lift": self.lift,
            "metric": self.metric,
            "target_value": self.target_value
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrengthTarget":
        return cls(
            lift=data["lift"],
            metric=data["metric"],
            target_value=data.get("target_value")
        )


@dataclass
class EnduranceTarget:
    """Target for endurance event."""
    sport: str  # "cycling", "running", "swimming"
    event_type: str  # "5k", "10k", "half_marathon", "marathon", "20min_power", "long_ride", "long_run"
    target_value: Optional[float] = None  # Optional target time/power/pace
    
    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "event_type": self.event_type,
            "target_value": self.target_value
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EnduranceTarget":
        return cls(
            sport=data["sport"],
            event_type=data["event_type"],
            target_value=data.get("target_value")
        )


@dataclass
class GoalConstraints:
    """Optional constraints for goal pursuit."""
    min_weekly_strength_sessions: Optional[int] = None
    min_weekly_endurance_sessions: Optional[int] = None
    max_weekly_sessions: Optional[int] = None
    avoid_exercises: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "min_weekly_strength_sessions": self.min_weekly_strength_sessions,
            "min_weekly_endurance_sessions": self.min_weekly_endurance_sessions,
            "max_weekly_sessions": self.max_weekly_sessions,
            "avoid_exercises": self.avoid_exercises
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "GoalConstraints":
        return cls(
            min_weekly_strength_sessions=data.get("min_weekly_strength_sessions"),
            min_weekly_endurance_sessions=data.get("min_weekly_endurance_sessions"),
            max_weekly_sessions=data.get("max_weekly_sessions"),
            avoid_exercises=data.get("avoid_exercises", [])
        )


@dataclass
class GoalConfig:
    """Configuration for a training goal."""
    goal_id: str
    athlete_id: str
    goal_type: GoalType
    target_date: date
    priority: str = "balanced"  # "strength", "endurance", "balanced"
    
    # Specific targets
    strength_targets: List[StrengthTarget] = field(default_factory=list)
    endurance_targets: List[EnduranceTarget] = field(default_factory=list)
    concurrent_target: Optional[ConcurrentTarget] = None
    
    # Constraints
    constraints: GoalConstraints = field(default_factory=GoalConstraints)
    
    # Metadata
    created_at: date = field(default_factory=date.today)
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "athlete_id": self.athlete_id,
            "goal_type": self.goal_type.value,
            "target_date": self.target_date.isoformat(),
            "priority": self.priority,
            "strength_targets": [t.to_dict() for t in self.strength_targets],
            "endurance_targets": [t.to_dict() for t in self.endurance_targets],
            "concurrent_target": self.concurrent_target.value if self.concurrent_target else None,
            "constraints": self.constraints.to_dict(),
            "created_at": self.created_at.isoformat(),
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "GoalConfig":
        return cls(
            goal_id=data["goal_id"],
            athlete_id=data["athlete_id"],
            goal_type=GoalType(data["goal_type"]),
            target_date=date.fromisoformat(data["target_date"]),
            priority=data.get("priority", "balanced"),
            strength_targets=[StrengthTarget.from_dict(t) for t in data.get("strength_targets", [])],
            endurance_targets=[EnduranceTarget.from_dict(t) for t in data.get("endurance_targets", [])],
            concurrent_target=ConcurrentTarget(data["concurrent_target"]) if data.get("concurrent_target") else None,
            constraints=GoalConstraints.from_dict(data.get("constraints", {})),
            created_at=date.fromisoformat(data.get("created_at", date.today().isoformat())),
            notes=data.get("notes", "")
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PhasePlan:
    """A single phase within a macrocycle."""
    phase_type: PhaseType
    start_date: date
    end_date: date
    duration_weeks: int
    
    # Phase-specific configuration
    target_sets_per_week: Optional[int] = None
    target_intensity: Optional[float] = None
    target_hiit_sessions: Optional[int] = None
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            "phase_type": self.phase_type.value,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "duration_weeks": self.duration_weeks,
            "target_sets_per_week": self.target_sets_per_week,
            "target_intensity": self.target_intensity,
            "target_hiit_sessions": self.target_hiit_sessions,
            "notes": self.notes
        }
    
    @property
    def is_active(self, today: date = None) -> bool:
        """Check if phase is active on given date."""
        today = today or date.today()
        return self.start_date <= today <= self.end_date


@dataclass
class MacrocycleContext:
    """Complete macrocycle plan for a goal."""
    goal_config: GoalConfig
    phases: List[PhasePlan]
    
    def to_dict(self) -> dict:
        return {
            "goal_config": self.goal_config.to_dict(),
            "phases": [p.to_dict() for p in self.phases]
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    def get_current_phase(self, today: date = None) -> Optional[PhasePlan]:
        """Get the phase active on given date."""
        today = today or date.today()
        for phase in self.phases:
            if phase.start_date <= today <= phase.end_date:
                return phase
        return None
    
    def get_phase_for_date(self, target_date: date) -> Optional[PhasePlan]:
        """Get the phase for a specific date."""
        for phase in self.phases:
            if phase.start_date <= target_date <= phase.end_date:
                return phase
        return None


@dataclass
class GoalState:
    """Current state of active goal pursuit."""
    goal_id: str
    athlete_id: str
    active: bool = True
    
    # Phase tracking
    current_phase: PhaseType = PhaseType.BASE
    phase_start_date: date = field(default_factory=date.today)
    phase_end_date: date = field(default_factory=date.today)
    last_phase_update_date: date = field(default_factory=date.today)
    
    # Progress tracking
    microcycles_completed_in_phase: int = 0
    
    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "athlete_id": self.athlete_id,
            "active": self.active,
            "current_phase": self.current_phase.value,
            "phase_start_date": self.phase_start_date.isoformat(),
            "phase_end_date": self.phase_end_date.isoformat(),
            "last_phase_update_date": self.last_phase_update_date.isoformat(),
            "microcycles_completed_in_phase": self.microcycles_completed_in_phase
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "GoalState":
        return cls(
            goal_id=data["goal_id"],
            athlete_id=data["athlete_id"],
            active=data.get("active", True),
            current_phase=PhaseType(data.get("current_phase", "base")),
            phase_start_date=date.fromisoformat(data["phase_start_date"]),
            phase_end_date=date.fromisoformat(data["phase_end_date"]),
            last_phase_update_date=date.fromisoformat(data["last_phase_update_date"]),
            microcycles_completed_in_phase=data.get("microcycles_completed_in_phase", 0)
        )


# ============================================================================
# Phase Scheduling (Deterministic)
# ============================================================================

def compute_phase_durations(time_to_event_days: int) -> Dict[PhaseType, int]:
    """
    Compute phase durations based on time to event.
    
    V1 deterministic rules:
    - >= 84d (12w): base:6w, build:4w, peak:1w, taper:1w
    - 56-83d (8-11w): base:4w, build:3w, peak:1w, taper:1w
    - 28-55d (4-7w): base:2w, build:1-2w (2w if >=42d else 1w), peak:1w, taper:1w
    - <28d: base:0-1w (1w if >=21d else 0), build:1w, peak:1w, taper:last 5-7d
    
    Args:
        time_to_event_days: Days from today to target event
    
    Returns:
        Dict of phase -> duration in weeks
    """
    if time_to_event_days >= 84:
        # 12+ weeks: full macrocycle
        return {
            PhaseType.BASE: 6,
            PhaseType.BUILD: 4,
            PhaseType.PEAK: 1,
            PhaseType.TAPER: 1
        }
    elif time_to_event_days >= 56:
        # 8-11 weeks: compressed
        return {
            PhaseType.BASE: 4,
            PhaseType.BUILD: 3,
            PhaseType.PEAK: 1,
            PhaseType.TAPER: 1
        }
    elif time_to_event_days >= 28:
        # 4-7 weeks: minimal base
        build_weeks = 2 if time_to_event_days >= 42 else 1
        return {
            PhaseType.BASE: 2,
            PhaseType.BUILD: build_weeks,
            PhaseType.PEAK: 1,
            PhaseType.TAPER: 1
        }
    else:
        # < 4 weeks: crash prep
        base_weeks = 1 if time_to_event_days >= 21 else 0
        taper_days = min(7, max(5, time_to_event_days - 14))  # Last 5-7 days
        taper_weeks = max(1, round(taper_days / 7))
        
        remaining = time_to_event_days - (base_weeks * 7) - (taper_weeks * 7)
        build_weeks = max(1, remaining // 14)  # Split remaining between build/peak
        peak_weeks = max(1, (remaining // 7) - build_weeks)
        
        result = {}
        if base_weeks > 0:
            result[PhaseType.BASE] = base_weeks
        result[PhaseType.BUILD] = build_weeks
        result[PhaseType.PEAK] = peak_weeks
        result[PhaseType.TAPER] = taper_weeks
        return result


def create_macrocycle(
    goal_config: GoalConfig,
    start_date: date = None
) -> MacrocycleContext:
    """
    Create complete macrocycle plan for a goal.
    
    Args:
        goal_config: Goal configuration
        start_date: Start date (default: today)
    
    Returns:
        MacrocycleContext with all phases scheduled
    """
    start_date = start_date or date.today()
    
    # Calculate time to event
    time_to_event = (goal_config.target_date - start_date).days
    if time_to_event < 7:
        raise ValueError("Target date must be at least 7 days in the future")
    
    # Get phase durations
    phase_durations = compute_phase_durations(time_to_event)
    
    # Create phases
    phases = []
    current_date = start_date
    
    for phase_type, duration_weeks in phase_durations.items():
        # Adjust taper if needed to hit target date exactly
        if phase_type == PhaseType.TAPER:
            days_remaining = (goal_config.target_date - current_date).days
            duration_weeks = max(1, round(days_remaining / 7))
        
        end_date = current_date + timedelta(weeks=duration_weeks) - timedelta(days=1)
        
        # Phase-specific targets based on goal type
        targets = _get_phase_targets(phase_type, goal_config.goal_type, goal_config.priority)
        
        phases.append(PhasePlan(
            phase_type=phase_type,
            start_date=current_date,
            end_date=end_date,
            duration_weeks=duration_weeks,
            target_sets_per_week=targets.get("sets_per_week"),
            target_intensity=targets.get("intensity"),
            target_hiit_sessions=targets.get("hiit_sessions"),
            notes=_get_phase_notes(phase_type, goal_config.goal_type)
        ))
        
        current_date = end_date + timedelta(days=1)
    
    return MacrocycleContext(
        goal_config=goal_config,
        phases=phases
    )


def _get_phase_targets(
    phase: PhaseType,
    goal_type: GoalType,
    priority: str
) -> Dict:
    """Get phase-specific training targets."""
    
    if goal_type == GoalType.STRENGTH_PEAK:
        # Strength-focused targets
        targets = {
            PhaseType.BASE: {"sets_per_week": 15, "intensity": 0.75, "hiit_sessions": 0},
            PhaseType.BUILD: {"sets_per_week": 12, "intensity": 0.82, "hiit_sessions": 0},
            PhaseType.PEAK: {"sets_per_week": 8, "intensity": 0.88, "hiit_sessions": 0},
            PhaseType.TAPER: {"sets_per_week": 5, "intensity": 0.85, "hiit_sessions": 0}
        }
    elif goal_type == GoalType.ENDURANCE_EVENT:
        # Endurance-focused targets
        targets = {
            PhaseType.BASE: {"sets_per_week": 6, "intensity": 0.70, "hiit_sessions": 1},
            PhaseType.BUILD: {"sets_per_week": 6, "intensity": 0.72, "hiit_sessions": 2},
            PhaseType.PEAK: {"sets_per_week": 4, "intensity": 0.75, "hiit_sessions": 2},
            PhaseType.TAPER: {"sets_per_week": 3, "intensity": 0.70, "hiit_sessions": 1}
        }
    else:  # CONCURRENT_EVENT
        # Balanced targets based on priority
        if priority == "strength":
            targets = {
                PhaseType.BASE: {"sets_per_week": 12, "intensity": 0.75, "hiit_sessions": 1},
                PhaseType.BUILD: {"sets_per_week": 10, "intensity": 0.82, "hiit_sessions": 1},
                PhaseType.PEAK: {"sets_per_week": 7, "intensity": 0.88, "hiit_sessions": 0},
                PhaseType.TAPER: {"sets_per_week": 4, "intensity": 0.85, "hiit_sessions": 0}
            }
        elif priority == "endurance":
            targets = {
                PhaseType.BASE: {"sets_per_week": 8, "intensity": 0.70, "hiit_sessions": 1},
                PhaseType.BUILD: {"sets_per_week": 7, "intensity": 0.72, "hiit_sessions": 2},
                PhaseType.PEAK: {"sets_per_week": 5, "intensity": 0.75, "hiit_sessions": 2},
                PhaseType.TAPER: {"sets_per_week": 3, "intensity": 0.70, "hiit_sessions": 1}
            }
        else:  # balanced
            targets = {
                PhaseType.BASE: {"sets_per_week": 10, "intensity": 0.72, "hiit_sessions": 1},
                PhaseType.BUILD: {"sets_per_week": 9, "intensity": 0.78, "hiit_sessions": 1},
                PhaseType.PEAK: {"sets_per_week": 6, "intensity": 0.82, "hiit_sessions": 1},
                PhaseType.TAPER: {"sets_per_week": 3, "intensity": 0.78, "hiit_sessions": 0}
            }
    
    return targets.get(phase, {})


def _get_phase_notes(phase: PhaseType, goal_type: GoalType) -> str:
    """Generate phase notes based on type."""
    notes = {
        PhaseType.BASE: "Build aerobic base and work capacity",
        PhaseType.BUILD: "Build event-specific fitness",
        PhaseType.PEAK: "Maximal efforts, minimal volume",
        PhaseType.TAPER: "Reduce fatigue, maintain sharpness"
    }
    
    if goal_type == GoalType.STRENGTH_PEAK:
        notes[PhaseType.BASE] = "Build muscle mass and technique"
        notes[PhaseType.BUILD] = "Build strength with heavy compounds"
        notes[PhaseType.PEAK] = "Peak intensity, minimal volume"
        notes[PhaseType.TAPER] = "Rest and neural potentiation"
    
    return notes.get(phase, "")


# ============================================================================
# Goal State Management
# ============================================================================

def create_goal_state(
    goal_config: GoalConfig,
    macrocycle: MacrocycleContext
) -> GoalState:
    """
    Create initial goal state from config and macrocycle.
    
    Args:
        goal_config: Goal configuration
        macrocycle: Computed macrocycle
    
    Returns:
        Initial GoalState
    """
    current_phase = macrocycle.get_current_phase()
    if not current_phase:
        current_phase = macrocycle.phases[0]
    
    return GoalState(
        goal_id=goal_config.goal_id,
        athlete_id=goal_config.athlete_id,
        active=True,
        current_phase=current_phase.phase_type,
        phase_start_date=current_phase.start_date,
        phase_end_date=current_phase.end_date,
        last_phase_update_date=date.today(),
        microcycles_completed_in_phase=0
    )


def advance_goal_state(
    goal_state: GoalState,
    macrocycle: MacrocycleContext
) -> GoalState:
    """
    Advance goal state to next phase if current phase is complete.
    
    Args:
        goal_state: Current goal state
        macrocycle: Macrocycle context
    
    Returns:
        Updated GoalState
    """
    today = date.today()
    
    # Check if we're past the current phase end date
    if today > goal_state.phase_end_date:
        # Find next phase
        next_phase = None
        for i, phase in enumerate(macrocycle.phases):
            if phase.phase_type == goal_state.current_phase and i < len(macrocycle.phases) - 1:
                next_phase = macrocycle.phases[i + 1]
                break
        
        if next_phase:
            goal_state.current_phase = next_phase.phase_type
            goal_state.phase_start_date = next_phase.start_date
            goal_state.phase_end_date = next_phase.end_date
            goal_state.last_phase_update_date = today
            goal_state.microcycles_completed_in_phase = 0
    
    return goal_state


# ============================================================================
# Program Engine Integration Helpers
# ============================================================================

def get_block_type_for_phase(phase: PhaseType) -> str:
    """
    Map goal phase to program engine block type.
    
    Args:
        phase: Goal phase type
    
    Returns:
        Block type string for program engine
    """
    mapping = {
        PhaseType.BASE: "base",
        PhaseType.BUILD: "build",
        PhaseType.PEAK: "peak",
        PhaseType.TAPER: "deload"  # Taper uses deload block type
    }
    return mapping.get(phase, "base")


def get_microcycle_targets_for_phase(
    phase: PhaseType,
    goal_config: GoalConfig
) -> Dict:
    """
    Get microcycle progression targets for current phase.
    
    Args:
        phase: Current phase
        goal_config: Goal configuration
    
    Returns:
        Dict with progression targets
    """
    targets = _get_phase_targets(phase, goal_config.goal_type, goal_config.priority)
    
    return {
        "target_sets_per_week": targets.get("sets_per_week", 10),
        "target_avg_intensity": targets.get("intensity", 0.75),
        "target_hiit_sessions": targets.get("hiit_sessions", 0),
        "volume_progression": 1.0 if phase == PhaseType.TAPER else (
            1.02 if phase == PhaseType.PEAK else 1.05
        )
    }


def should_prioritize_lift_for_goal(
    lift: str,
    goal_config: GoalConfig
) -> bool:
    """
    Check if a lift should be prioritized based on goal.
    
    Args:
        lift: Lift name
        goal_config: Goal configuration
    
    Returns:
        True if lift should be prioritized
    """
    if goal_config.goal_type == GoalType.STRENGTH_PEAK:
        return any(t.lift == lift for t in goal_config.strength_targets)
    elif goal_config.goal_type == GoalType.CONCURRENT_EVENT:
        return any(t.lift == lift for t in goal_config.strength_targets)
    return False


def get_endurance_focus_for_goal(
    goal_config: GoalConfig
) -> Optional[str]:
    """
    Get endurance focus based on goal.
    
    Args:
        goal_config: Goal configuration
    
    Returns:
        Event type string or None
    """
    if goal_config.endurance_targets:
        return goal_config.endurance_targets[0].event_type
    return None


# ============================================================================
# Phase Guardrails for Performance Adjustments
# ============================================================================

def should_apply_phase_guardrails(
    phase: str,
    proposed_adjustment: Dict
) -> Dict:
    """
    Apply phase guardrails to performance adjustments.
    
    Rules:
    - Taper: cannot increase volume, only small intensity touches
    - Peak: no extra volume, allow slight intensity adjustment
    - Base/Build: normal performance feedback
    
    Args:
        phase: Current phase string
        proposed_adjustment: Performance adjustment dict
    
    Returns:
        Adjusted adjustment dict
    """
    adjusted = dict(proposed_adjustment)
    
    if phase == PhaseType.TAPER.value:
        # Taper: cannot increase volume
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        if adjusted.get("add_hiit_intervals", 0) > 0:
            adjusted["add_hiit_intervals"] = 0
        # Allow small intensity adjustment only
        if adjusted.get("intensity_adjustment_pct", 0) > 0.02:
            adjusted["intensity_adjustment_pct"] = 0.02
        adjusted["phase_guardrail_applied"] = "taper_volume_locked"
    
    elif phase == PhaseType.PEAK.value:
        # Peak: no extra volume
        if adjusted.get("volume_adjustment_pct", 0) > 0:
            adjusted["volume_adjustment_pct"] = 0
        if adjusted.get("add_stimulus_lifts"):
            adjusted["add_stimulus_lifts"] = []
        adjusted["phase_guardrail_applied"] = "peak_no_extra_volume"
    
    return adjusted
