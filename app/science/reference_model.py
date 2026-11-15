"""Small nested forecasting reference, independent of the production database.

No physiological compartment claims or optimal-training claims. Parameters are
explicit candidate settings, not population estimates. See docs/research_protocol.md.
"""
from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True)
class Parameters:
    alpha: float = 0.1
    tau_strength_days: float = 3.0
    tau_endurance_days: float = 2.0
    k_strength: float = 0.005
    k_endurance: float = 0.001

    def __post_init__(self):
        if not all(math.isfinite(v) for v in vars(self).values()):
            raise ValueError("Parameters must be finite")
        if not 0 < self.alpha <= 1 or min(self.tau_strength_days, self.tau_endurance_days) <= 0:
            raise ValueError("Invalid smoothing gain or time constant")
        if min(self.k_strength, self.k_endurance) < 0:
            raise ValueError("Fatigue coefficients must be nonnegative")


class ForecastModel:
    """M0: slow log-performance; M1: + strength dose; M2: + endurance dose.

    log(v/v_ref) = c - d_strength - d_endurance + error.
    States d decay exactly in elapsed days; an event adds k*u afterward.
    c is updated from observed residuals, never from future observations.
    Only M2 uses endurance; M0/M1/M2 are nested at k_strength/k_endurance=0.
    """
    def __init__(self, variant='M0', params=None):
        if variant not in {'M0', 'M1', 'M2'}:
            raise ValueError("Unknown nested model")
        self.variant = variant
        self.params = params or Parameters()
        self.c = self.ds = self.de = 0.0
        self.at = None

    def advance(self, at: datetime):
        if self.at is not None:
            days = (at - self.at).total_seconds() / 86400
            if days < 0:
                raise ValueError("Events must be chronological")
            self.ds *= math.exp(-days / self.params.tau_strength_days)
            self.de *= math.exp(-days / self.params.tau_endurance_days)
        self.at = at

    def predict(self, reference_velocity: float) -> float:
        if not math.isfinite(reference_velocity) or reference_velocity <= 0:
            raise ValueError("Reference velocity must be positive and finite")
        return reference_velocity * math.exp(self.c - self.ds - self.de)

    def observe(self, velocity: float, reference_velocity: float):
        if not math.isfinite(velocity) or velocity <= 0:
            raise ValueError("Observed velocity must be finite and positive")
        error = math.log(velocity / reference_velocity) - (self.c - self.ds - self.de)
        self.c += self.params.alpha * error

    def add_dose(self, strength: float = 0.0, endurance: float = 0.0):
        if not all(math.isfinite(v) and v >= 0 for v in (strength, endurance)):
            raise ValueError("Doses must be finite and nonnegative")
        if self.variant in {'M1', 'M2'}:
            self.ds += self.params.k_strength * strength
        if self.variant == 'M2':
            self.de += self.params.k_endurance * endurance
