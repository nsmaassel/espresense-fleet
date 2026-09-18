"""Normalize only approved evidence; rejected payloads are never returned or logged."""
import json
import math
import re


def _object(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result

    if not isinstance(payload, (str, bytes)) or len(payload) > 16384:
        raise ValueError("Invalid payload")
    data = json.loads(payload, object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    return data


def _number(value, low, high):
    return (type(value) in (int, float) and low <= value <= high
            and math.isfinite(value))


def device_observation(payload, retained):
    """Return (distance_m, optional rssi_dbm), or None for unusable evidence."""
    if retained:
        return None
    try:
        data = _object(payload)
        distance, rssi = data.get("distance"), data.get("rssi")
        if not _number(distance, 0, 10000):
            return None
        if "rssi" in data and not _number(rssi, -200, 0):
            return None
        return distance, rssi
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _zones(value):
    if (not isinstance(value, list) or len(value) > 128
            or any(not isinstance(zone, str) or len(zone) > 128 for zone in value)):
        raise ValueError("Invalid zone collection")
    return set(value)


def camera_events(payload, retained, config, *, wall_now, monotonic_now):
    """Convert newly entered current zones to per-door events with monotonic time.

    Frigate's frame time orders camera evidence against actual door transitions.
    Receiver freshness alone cannot make an old camera frame current.
    """
    if retained:
        return []
    try:
        data = _object(payload)
        after, before = data.get("after"), data.get("before", {})
        if data.get("type") not in ("new", "update") or not isinstance(after, dict):
            return []
        if after.get("label") != "cat" or after.get("false_positive") is not False:
            return []
        if after.get("end_time") is not None:
            return []
        event_id, frame = after.get("id"), after.get("frame_time")
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", event_id):
            return []
        if not _number(wall_now, 0, 10**12) or not _number(monotonic_now, 0, 10**12):
            return []
        if not _number(frame, wall_now - config["timing"]["observation_fresh_s"], wall_now):
            return []
        if not isinstance(before, dict):
            return []
        newly_entered = _zones(after.get("current_zones")) - _zones(before.get("current_zones", []))
        evidence_at = monotonic_now - (wall_now - frame)
        if evidence_at < 0:
            return []
        events = []
        for door, mapping in config["doors"].items():
            if not mapping["exterior"] or mapping["camera"] != after.get("camera"):
                continue
            if newly_entered.intersection(mapping["outside_zones"]):
                zone = "outside"
            elif newly_entered.intersection(mapping["inside_zones"]):
                zone = "inside"
            else:
                continue
            events.append({"door": door, "zone": zone, "event_id": event_id,
                           "evidence_at": evidence_at})
        return events
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return []
