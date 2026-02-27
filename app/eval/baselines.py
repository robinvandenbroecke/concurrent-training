"""
Sprint V1: Baseline Models for Comparison

Simple, interpretable baselines with fixed parameters.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta
import math
import statistics


@dataclass
class BanisterState:
    """Simple fitness-fatigue state (Banister-style)."""
    fitness: float = 1.0
    fatigue: float = 0.0
    
    @property
    def form(self) -> float:
        """Form = fitness - fatigue (higher is better)."""
        return self.fitness - self.fatigue
    
    def predicted_perf_y(self) -> float:
        """Map form to predicted perf_y."""
        # Normalize form to 0-1 range (rough approximation)
        norm = max(0.0, min(1.0, 0.5 + self.form))
        return 0.75 + 0.25 * norm


@dataclass
class BanisterParams:
    """Fixed parameters for Banister model (<= 6 parameters)."""
    tau_fitness: float = 30.0  # days
    tau_fatigue: float = 7.0   # days
    k_fitness: float = 0.02    # gain per unit impulse
    k_fatigue: float = 0.04    # gain per unit impulse
    
    def update(self, state: BanisterState, impulse: float, days: int = 1) -> BanisterState:
        """Update state given training impulse."""
        # Decay
        fitness_decay = state.fitness * math.exp(-days / self.tau_fitness)
        fatigue_decay = state.fatigue * math.exp(-days / self.tau_fatigue)
        
        # Add from impulse
        new_fitness = fitness_decay + self.k_fitness * impulse
        new_fatigue = fatigue_decay + self.k_fatigue * impulse
        
        return BanisterState(fitness=new_fitness, fatigue=new_fatigue)


class BaselineVelocityThreshold:
    """
    Baseline A: Velocity-threshold heuristic.
    
    Maintains rolling 7-day reference perf_y and uses ratio as readiness proxy.
    """
    
    def __init__(self, window_days: int = 7):
        self.window_days = window_days
        self.history: Dict[str, List[Tuple[date, float]]] = {}  # lift -> [(date, perf_y)]
    
    def add_observation(self, lift: str, obs_date: date, perf_y: float):
        """Record an observed performance."""
        if lift not in self.history:
            self.history[lift] = []
        self.history[lift].append((obs_date, perf_y))
    
    def get_reference_perf_y(self, lift: str, ref_date: date) -> Optional[float]:
        """Get median perf_y over window_days before ref_date."""
        if lift not in self.history:
            return None
        
        window_start = ref_date - timedelta(days=self.window_days)
        window_values = [
            py for d, py in self.history[lift]
            if window_start <= d < ref_date
        ]
        
        if not window_values:
            return None
        
        return statistics.median(window_values)
    
    def predict_readiness(self, lift: str, ref_date: date) -> float:
        """
        Predict readiness based on ratio of recent perf_y to reference.
        Returns 0-1 readiness score.
        """
        # Get most recent observation
        if lift not in self.history or not self.history[lift]:
            return 0.75  # Default neutral
        
        # Most recent perf_y
        recent = self.history[lift][-1][1]
        
        # Reference (median over window)
        reference = self.get_reference_perf_y(lift, ref_date)
        if reference is None:
            return 0.75
        
        # Ratio clamped to 0-1
        ratio = recent / reference if reference > 0 else 0.75
        return max(0.0, min(1.0, ratio))
    
    def predict_perf_y(self, lift: str, ref_date: date) -> float:
        """Predict next-day perf_y using baseline heuristic."""
        readiness = self.predict_readiness(lift, ref_date)
        return 0.75 + 0.25 * readiness


class BaselineBanister:
    """
    Baseline B: Simple Banister-style fitness-fatigue model.
    
    Separate states per lift with fixed parameters.
    """
    
    def __init__(self):
        self.params = BanisterParams()
        self.states: Dict[str, BanisterState] = {}  # lift -> state
        self.last_update: Dict[str, date] = {}  # lift -> last date
    
    def _get_or_create_state(self, lift: str) -> BanisterState:
        """Get or initialize state for a lift."""
        if lift not in self.states:
            self.states[lift] = BanisterState(fitness=1.0, fatigue=0.0)
        return self.states[lift]
    
    def compute_impulse(self, tonnage: float, intensity: float) -> float:
        """Compute training impulse from tonnage and intensity."""
        # Simple impulse: tonnage * intensity^1.2 normalized
        return tonnage * (intensity ** 1.2) / 1000.0
    
    def update(self, lift: str, obs_date: date, tonnage: float, intensity: float):
        """Update model with training session."""
        state = self._get_or_create_state(lift)
        
        # Compute days since last update
        days = 1
        if lift in self.last_update:
            days = max(1, (obs_date - self.last_update[lift]).days)
        
        # Compute impulse
        impulse = self.compute_impulse(tonnage, intensity)
        
        # Update state
        new_state = self.params.update(state, impulse, days)
        self.states[lift] = new_state
        self.last_update[lift] = obs_date
    
    def predict_readiness(self, lift: str) -> float:
        """Predict readiness (0-1) from current form."""
        state = self._get_or_create_state(lift)
        # Map form to readiness (0-1)
        form = state.form
        return max(0.0, min(1.0, 0.5 + form))
    
    def predict_perf_y(self, lift: str) -> float:
        """Predict next-day perf_y."""
        state = self._get_or_create_state(lift)
        return state.predicted_perf_y()


class BaselineEndurance:
    """
    Baseline for endurance: simple volume trend.
    
    Uses recent volume (TSS proxy) trend to predict stable/decline.
    """
    
    def __init__(self, window_days: int = 7):
        self.window_days = window_days
        self.history: List[Tuple[date, float]] = []  # [(date, load_proxy)]
    
    def add_observation(self, obs_date: date, load_proxy: float):
        """Record an endurance session."""
        self.history.append((obs_date, load_proxy))
    
    def predict_stable(self, ref_date: date) -> bool:
        """
        Predict if next-day performance will be stable or improve.
        Returns True for stable/improve, False for decline.
        """
        if len(self.history) < 3:
            return True  # Default optimistic
        
        # Get recent loads
        recent_cutoff = ref_date - timedelta(days=self.window_days)
        recent_loads = [load for d, load in self.history if d >= recent_cutoff]
        older_loads = [load for d, load in self.history if d < recent_cutoff]
        
        if not recent_loads or not older_loads:
            return True
        
        recent_avg = statistics.mean(recent_loads)
        older_avg = statistics.mean(older_loads)
        
        # If load is increasing or stable, predict stable performance
        return recent_avg >= older_avg * 0.9  # Allow 10% decrease
