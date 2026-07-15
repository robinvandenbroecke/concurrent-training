"""Power-first endurance load construction with explicit fallbacks.

The output uses minute-equivalent stress units so it remains compatible with
the existing day engine while power-aware inputs are introduced incrementally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence
import math


@dataclass(frozen=True)
class EnduranceLoad:
    u_z2: float
    u_hiit: float
    total: float
    intensity_type: str
    signal_source: str
    average_power_w: Optional[float] = None
    normalized_power_w: Optional[float] = None
    intensity_factor: Optional[float] = None
    threshold_power_w: Optional[float] = None


def _valid_power_values(power_data: Optional[Sequence[Mapping]]) -> list[float]:
    values: list[float] = []
    for point in power_data or []:
        try:
            value = float(point.get("power"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            values.append(value)
    return values


def _estimate_normalized_power(values: Sequence[float]) -> Optional[float]:
    """Deterministic fourth-power approximation when a stream is available."""
    if not values:
        return None
    fourth_mean = sum(value ** 4 for value in values) / len(values)
    return fourth_mean ** 0.25


def compute_endurance_load(
    *,
    sport: str,
    duration_minutes: float,
    declared_intensity: str,
    power_data: Optional[Sequence[Mapping]] = None,
    average_power_w: Optional[float] = None,
    normalized_power_w: Optional[float] = None,
    threshold_power_w: Optional[float] = None,
) -> EnduranceLoad:
    """Compute endurance impulses using power whenever it is interpretable.

    Cycling and reliable running-power sessions use threshold-relative power.
    If threshold power is unavailable, power is retained as context but the
    declared intensity remains the classification source. Duration-only input
    is the final fallback.
    """
    duration = max(0.0, float(duration_minutes))
    values = _valid_power_values(power_data)
    avg_power = average_power_w
    if avg_power is None and values:
        avg_power = sum(values) / len(values)
    np_power = normalized_power_w or _estimate_normalized_power(values) or avg_power

    power_capable = sport in {"cycling", "running"}
    threshold = float(threshold_power_w) if threshold_power_w and threshold_power_w > 0 else None
    if power_capable and np_power and threshold:
        intensity_factor = max(0.30, min(1.50, float(np_power) / threshold))
        # Minute-equivalent power load. Squaring IF preserves compatibility with
        # duration-based state coefficients while making harder work costlier.
        total = duration * intensity_factor ** 2

        if values:
            z2_count = sum(1 for value in values if value < 0.85 * threshold)
            hiit_count = sum(1 for value in values if value >= 0.95 * threshold)
            middle_count = len(values) - z2_count - hiit_count
            z2_fraction = (z2_count + 0.5 * middle_count) / len(values)
            hiit_fraction = (hiit_count + 0.5 * middle_count) / len(values)
        elif intensity_factor < 0.85:
            z2_fraction, hiit_fraction = 1.0, 0.0
        elif intensity_factor >= 0.95:
            z2_fraction, hiit_fraction = 0.0, 1.0
        else:
            hiit_fraction = (intensity_factor - 0.85) / 0.10
            z2_fraction = 1.0 - hiit_fraction

        u_z2 = total * z2_fraction
        u_hiit = total * hiit_fraction
        if u_hiit <= 0.05 * total:
            intensity_type = "z2"
        elif u_z2 <= 0.05 * total:
            intensity_type = "hiit"
        else:
            intensity_type = "mixed"
        return EnduranceLoad(
            u_z2=u_z2,
            u_hiit=u_hiit,
            total=total,
            intensity_type=intensity_type,
            signal_source="power",
            average_power_w=avg_power,
            normalized_power_w=np_power,
            intensity_factor=intensity_factor,
            threshold_power_w=threshold,
        )

    # Power without a threshold is useful metadata, but not sufficient for an
    # athlete-specific zone decision. Use the declared label and mark the source.
    signal_source = "power_unscaled" if power_capable and np_power else "summary"
    if declared_intensity == "hiit":
        u_z2, u_hiit = 0.0, duration
    elif declared_intensity == "mixed":
        u_z2, u_hiit = 0.3 * duration, 0.7 * duration
    else:
        u_z2, u_hiit = duration, 0.0
    return EnduranceLoad(
        u_z2=u_z2,
        u_hiit=u_hiit,
        total=u_z2 + u_hiit,
        intensity_type=declared_intensity if declared_intensity in {"z2", "hiit", "mixed"} else "z2",
        signal_source=signal_source,
        average_power_w=avg_power,
        normalized_power_w=np_power,
        threshold_power_w=threshold,
    )
