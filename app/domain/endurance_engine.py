"""Threshold-relative external load, in minute-equivalent heuristic units.

This is neither TSS nor CP/W′. Stream load is integral((P/threshold)^2 dt)/60.
Zeros are valid coasting measurements. Supplied normalized power is retained;
we never label a raw fourth-power mean as Normalized Power.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence
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
    load_method: str = "declared_intensity_duration"
    sampling_assumption: Optional[str] = None


def _finite(value, name: str, minimum: float = 0.0) -> float:
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return result


def _segments(power_data: Sequence[Mapping], duration_seconds: float):
    """Piecewise constant power; each timestamp starts a segment.

    Relative timestamps must start at zero and increase strictly. The final
    sample extends to the supplied duration. Untimed legacy arrays use equal
    intervals over that duration and expose that assumption in the output.
    Missing/invalid points are rejected rather than compressing the clock.
    """
    if not power_data:
        return [], None
    values = [_finite(p.get("power"), "power") for p in power_data]
    times = [p.get("timestamp") for p in power_data]
    if all(t is None for t in times):
        return [(p, duration_seconds / len(values)) for p in values], "equal_intervals_assumed"
    if any(t is None for t in times):
        raise ValueError("Power timestamps must be present for every point or absent for all")
    times = [_finite(t, "timestamp") for t in times]
    if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])) or times[-1] > duration_seconds:
        raise ValueError("Power timestamps must start at zero, increase and fit within session duration")
    return [(p, end - start) for p, start, end in zip(values, times, times[1:] + [duration_seconds]) if end > start], "left_hold_between_timestamps"


def _high_fraction(relative_power: float) -> float:
    # Compatibility buckets only: not measured LT1/LT2 or proof of HIIT.
    return max(0.0, min(1.0, (relative_power - 0.85) / 0.10))


def compute_endurance_load(
    *, sport: str, duration_minutes: float, declared_intensity: str,
    power_data: Optional[Sequence[Mapping]] = None,
    average_power_w: Optional[float] = None,
    normalized_power_w: Optional[float] = None,
    threshold_power_w: Optional[float] = None,
) -> EnduranceLoad:
    duration = _finite(duration_minutes, "duration_minutes")
    if declared_intensity not in {"z2", "hiit", "mixed"}:
        raise ValueError("Unknown declared endurance intensity")
    average = _finite(average_power_w, "average_power_w") if average_power_w is not None else None
    supplied_np = _finite(normalized_power_w, "normalized_power_w") if normalized_power_w is not None else None
    threshold = _finite(threshold_power_w, "threshold_power_w") if threshold_power_w is not None else None
    if threshold == 0:
        raise ValueError("threshold_power_w must be positive")
    segments, assumption = _segments(power_data or [], duration * 60)
    if segments and duration > 0:
        average = sum(p * seconds for p, seconds in segments) / (duration * 60)
    power_capable = sport in {"cycling", "running"}
    effective_summary = supplied_np if supplied_np is not None else average
    has_power = bool(segments) or effective_summary is not None
    if power_capable and has_power and threshold is not None:
        if segments:
            total = sum((p / threshold) ** 2 * seconds / 60 for p, seconds in segments)
            high = sum((p / threshold) ** 2 * seconds / 60 * _high_fraction(p / threshold) for p, seconds in segments)
            factor = math.sqrt(total / duration) if duration else 0.0
            method = "relative_power_squared_time_integral"
        else:
            factor = effective_summary / threshold
            total = duration * factor ** 2
            high = total * _high_fraction(factor)
            method = "supplied_np_squared_duration" if supplied_np is not None else "average_power_squared_duration"
        low = max(0.0, total - high)
        label = "z2" if total == 0 or high <= .05 * total else "hiit" if low <= .05 * total else "mixed"
        return EnduranceLoad(low, high, total, label, "power", average, supplied_np, factor, threshold, method, assumption)
    source = "power_unscaled" if power_capable and has_power else "summary"
    fraction = {"z2": 0.0, "hiit": 1.0, "mixed": 0.7}[declared_intensity]
    return EnduranceLoad(duration - duration * fraction, duration * fraction, duration,
                         declared_intensity, source, average, supplied_np, None, threshold,
                         "declared_intensity_duration", assumption)
