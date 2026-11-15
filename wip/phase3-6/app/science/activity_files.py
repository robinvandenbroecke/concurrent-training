"""Parse an activity file the user exported themselves (FIT, TCX or GPX).

Output is one normalised record with explicit units and provenance. Rules:

* power in watts, heart rate in beats/min, cadence in rev/min, time in seconds;
* the 1 Hz series keeps ``None`` where the recorder had no sample: a gap is
  never filled with zero or with interpolated values;
* nothing is inferred that the file does not contain (no power from speed, no
  threshold, no training zones);
* FIT developer fields and vendor-specific messages are ignored.

FIT decoding uses the MIT-licensed ``fitdecode`` package and the public FIT
profile. XML is parsed with ``defusedxml`` (no entity expansion, no network).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import math
from typing import Dict, List, Optional

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 6 * 3600
SPORTS = {"cycling": "cycling", "biking": "cycling", "bike": "cycling", "virtual_ride": "cycling",
          "running": "running", "run": "running", "swimming": "swimming", "swim": "swimming"}


class ActivityFileError(ValueError):
    pass


def _sport(value) -> str:
    return SPORTS.get(str(value or "").strip().lower(), "other")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _number(value, low: float, high: float) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def _normalise(samples: List[dict], sport: str, source_format: str, device: Optional[dict], digest: str) -> dict:
    samples = sorted((s for s in samples if s.get("t") is not None), key=lambda s: s["t"])
    if len(samples) < 2:
        raise ActivityFileError("The file contains no timed samples")
    start = samples[0]["t"]
    elapsed = int(round((samples[-1]["t"] - start).total_seconds()))
    if elapsed <= 0:
        raise ActivityFileError("The file has no positive duration")
    if elapsed > MAX_SECONDS:
        raise ActivityFileError("Activities longer than 6 hours are not supported by this import")
    series: Dict[str, List[Optional[float]]] = {k: [None] * (elapsed + 1) for k in ("power", "heart_rate", "cadence")}
    for s in samples:
        index = int(round((s["t"] - start).total_seconds()))
        for key in series:
            if s.get(key) is not None:
                series[key][index] = s[key]   # the last sample within a second wins
    result = {
        "format": source_format, "file_sha256": digest, "sport": sport,
        "start_time": start.isoformat().replace("+00:00", "Z"), "elapsed_seconds": elapsed,
        "device": device or None, "sample_seconds": 1, "channels": {},
    }
    for key, values in series.items():
        known = [v for v in values if v is not None]
        if not known:
            continue
        result["channels"][key] = {
            "unit": {"power": "W", "heart_rate": "bpm", "cadence": "rpm"}[key],
            "values": [None if v is None else int(round(v)) for v in values],
            "samples": len(known), "missing_seconds": len(values) - len(known),
            # Mean over recorded seconds only; coverage is reported separately.
            "mean_recorded": round(sum(known) / len(known), 1),
        }
    power = series["power"]
    if any(v is not None for v in power):
        known = [v for v in power if v is not None]
        result["power_summary"] = {
            "recorded_seconds": len(known), "missing_seconds": len(power) - len(known),
            "mean_w": round(sum(known) / len(known), 2), "sum_squares_w2s": round(sum(v * v for v in known), 1),
            "mean_maximal_w": _mean_maximal(power),
        }
    return result


MEAN_MAXIMAL_SECONDS = (5, 60, 180, 300, 480, 720, 1200)


def _mean_maximal(power: List[Optional[float]]) -> Dict[str, float]:
    """Best mean power per duration over windows WITHOUT a missing sample.

    These are candidates the athlete may confirm as maximal efforts; a high
    mean in ordinary training is not automatically a maximal effort.
    """
    total, gaps = [0.0], [0]
    for value in power:
        total.append(total[-1] + (value or 0.0))
        gaps.append(gaps[-1] + (value is None))
    best: Dict[str, float] = {}
    for window in MEAN_MAXIMAL_SECONDS:
        values = [(total[i + window] - total[i]) / window for i in range(len(power) - window + 1)
                  if gaps[i + window] == gaps[i]]
        if values:
            best[str(window)] = round(max(values), 1)
    return best


def _parse_fit(data: bytes, digest: str) -> dict:
    import fitdecode

    samples, sport, device = [], "other", {}
    try:
        with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE,
                                 error_handling=fitdecode.ErrorHandling.RAISE) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                get = lambda name: frame.get_value(name, fallback=None)  # noqa: E731
                if frame.name == "record":
                    stamp = get("timestamp")
                    if isinstance(stamp, datetime):
                        samples.append({"t": _utc(stamp), "power": _number(get("power"), 0, 3000),
                                        "heart_rate": _number(get("heart_rate"), 20, 250),
                                        "cadence": _number(get("cadence"), 0, 250)})
                elif frame.name in {"sport", "session"} and sport == "other":
                    sport = _sport(get("sport"))
                elif frame.name == "file_id" and not device:
                    device = {k: str(v) for k, v in (("manufacturer", get("manufacturer")), ("product", get("product")),
                                                     ("serial_number", get("serial_number"))) if v is not None}
    except ActivityFileError:
        raise
    except Exception as exc:  # fitdecode raises several unrelated exception types
        raise ActivityFileError("The FIT file is damaged or not a valid activity file") from exc
    return _normalise(samples, sport, "fit", device, digest)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _time(text: Optional[str]) -> Optional[datetime]:
    try:
        return _utc(datetime.fromisoformat(text.strip().replace("Z", "+00:00")))
    except (AttributeError, ValueError):
        return None


def _parse_xml(data: bytes, digest: str) -> dict:
    from defusedxml import ElementTree

    try:
        root = ElementTree.fromstring(data)
    except Exception as exc:
        raise ActivityFileError("The file is not valid TCX or GPX") from exc
    kind = _local(root.tag).lower()
    samples, sport = [], "other"
    if kind == "trainingcenterdatabase":
        for element in root.iter():
            name = _local(element.tag)
            if name == "Activity" and sport == "other":
                sport = _sport(element.attrib.get("Sport"))
            if name != "Trackpoint":
                continue
            point = {"t": None, "power": None, "heart_rate": None, "cadence": None}
            for child in element.iter():
                tag = _local(child.tag)
                if tag == "Time":
                    point["t"] = _time(child.text)
                elif tag == "Watts":
                    point["power"] = _number(child.text, 0, 3000)
                elif tag in {"Cadence", "RunCadence"}:
                    point["cadence"] = _number(child.text, 0, 250)
                elif tag == "HeartRateBpm":
                    point["heart_rate"] = _number(next((g.text for g in child if _local(g.tag) == "Value"), None), 20, 250)
            samples.append(point)
        return _normalise(samples, sport, "tcx", None, digest)
    if kind == "gpx":
        for element in root.iter():
            name = _local(element.tag)
            if name == "type" and sport == "other":
                sport = _sport(element.text)
            if name != "trkpt":
                continue
            point = {"t": None, "power": None, "heart_rate": None, "cadence": None}
            for child in element.iter():
                tag = _local(child.tag).lower()
                if tag == "time":
                    point["t"] = _time(child.text)
                elif tag in {"power", "watts"}:
                    point["power"] = _number(child.text, 0, 3000)
                elif tag == "hr":
                    point["heart_rate"] = _number(child.text, 20, 250)
                elif tag == "cad":
                    point["cadence"] = _number(child.text, 0, 250)
            samples.append(point)
        return _normalise(samples, sport, "gpx", None, digest)
    raise ActivityFileError("Only FIT, TCX and GPX activity files are supported")


def parse_activity_file(data: bytes) -> dict:
    if not data:
        raise ActivityFileError("The file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise ActivityFileError("The file is larger than 12 MB")
    digest = hashlib.sha256(data).hexdigest()
    if len(data) >= 12 and data[8:12] == b".FIT":
        return _parse_fit(data, digest)
    if data[:2] == b"PK":
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [n for n in archive.namelist() if n.lower().endswith(".fit")]
                if len(names) != 1 or archive.getinfo(names[0]).file_size > MAX_FILE_BYTES:
                    raise ActivityFileError("The archive must contain exactly one FIT file")
                return _parse_fit(archive.read(names[0]), digest)
        except zipfile.BadZipFile as exc:
            raise ActivityFileError("The archive is damaged") from exc
    head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"<"):
        return _parse_xml(data, digest)
    raise ActivityFileError("Only FIT, TCX and GPX activity files are supported")
