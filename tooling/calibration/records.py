"""Strict versioned evidence contracts. Validation errors never include input data."""
import json
import math
import re
from pathlib import Path

MAX_MS = 3_600_000
MAX_RECORDS = 200_000
MAX_BYTES = 64 * 1024 * 1024


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number within the documented bounds")
    if not low <= value <= high or not math.isfinite(value):
        raise ValueError("Expected a finite number within the documented bounds")
    return value


def integer(value, low, high):
    number(value, low, high)
    if not isinstance(value, int):
        raise ValueError("Expected an integer within the documented bounds")
    return value


def alias(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", value)
            or re.fullmatch(r"[a-f0-9]{12,}", value)
            or re.fullmatch(r"(?:[a-f0-9]{2}-){5}[a-f0-9]{2}", value)
            or value.startswith("irk")):
        raise ValueError("Use a short lowercase alias, never a credential or raw identifier")
    return value


def fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError("Missing or unsupported fields")
    if "schema" in obj and (type(obj["schema"]) is not int or obj["schema"] != 1):
        raise ValueError("Unsupported schema")


def parse_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Invalid JSON document") from None


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("JSON document is too large")
    return parse_json(path.read_text(encoding="utf-8"))


def validate_schedule(data):
    fields(data, ("schema", "window_ms", "nodes", "stops"), ("router_separation_m",))
    window = integer(data["window_ms"], 100, 60_000)
    nodes = data["nodes"]
    if not isinstance(nodes, dict) or not 1 <= len(nodes) <= 64:
        raise ValueError("Schedule requires 1 to 64 mapped nodes")
    for node, room in nodes.items():
        alias(node)
        alias(room)
    stops = data["stops"]
    if not isinstance(stops, list) or not 1 <= len(stops) <= 200:
        raise ValueError("Schedule requires 1 to 200 stops")
    previous_end = 0
    windows = 0
    for stop in stops:
        fields(stop, ("room", "start_ms", "end_ms"))
        if stop["room"] not in nodes.values():
            raise ValueError("Stop room has no mapped node")
        start = integer(stop["start_ms"], 0, MAX_MS)
        end = integer(stop["end_ms"], 0, MAX_MS)
        if start < previous_end or end <= start:
            raise ValueError("Stops must be ordered, nonoverlapping, positive intervals")
        previous_end = end
        windows += math.ceil((end - start) / window)
    if windows > 10_000:
        raise ValueError("Schedule has too many windows")
    separation = data.get("router_separation_m", {})
    if not isinstance(separation, dict) or separation.keys() - nodes.keys():
        raise ValueError("Router measurements reference unmapped nodes")
    for value in separation.values():
        number(value, 0, 1000)
    return data


def validate_record(row):
    if not isinstance(row, dict):
        raise ValueError("Expected an observation object")
    kind = row.get("kind")
    required = {"schema", "kind", "elapsed_ms", "node"}
    if kind == "device":
        required.add("distance_m")
        optional = {"rssi_dbm", "retained"}
    elif kind == "wifi":
        required.add("rssi_dbm")
        optional = {"retained"}
    elif kind == "node_distance":
        required.update(("peer", "distance_m"))
        optional = {"retained"}
    else:
        raise ValueError("Unsupported observation kind")
    fields(row, required, optional)
    integer(row["elapsed_ms"], 0, MAX_MS)
    alias(row["node"])
    if "peer" in row:
        alias(row["peer"])
        if row["peer"] == row["node"]:
            raise ValueError("Directional observations require different nodes")
    if "distance_m" in row:
        number(row["distance_m"], 0, 10_000)
    if "rssi_dbm" in row:
        number(row["rssi_dbm"], -200, 0)
    if "retained" in row and type(row["retained"]) is not bool:
        raise ValueError("Retained must be a boolean")
    return row


def load_log(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Evidence file is too large")
    records, start, end = [], None, None
    previous, count, retained = -1, 0, 0
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if len(line) > 4096 or index > MAX_RECORDS + 1:
                raise ValueError("Evidence exceeds size or record limits")
            row = parse_json(line)
            if index == 0:
                fields(row, ("schema", "kind", "source", "duration_ms"))
                if row["kind"] != "capture_start" or row["source"] not in ("synthetic", "mqtt"):
                    raise ValueError("Missing evidence header")
                integer(row["duration_ms"], 1, MAX_MS)
                start = row
                continue
            if end is not None:
                raise ValueError("Data after evidence footer")
            if isinstance(row, dict) and row.get("kind") == "capture_end":
                fields(row, ("schema", "kind", "elapsed_ms", "records", "complete", "reason", "retained", "ignored", "invalid"))
                for key in ("records", "retained", "ignored", "invalid"):
                    integer(row[key], 0, 10_000_000)
                integer(row["elapsed_ms"], 0, start["duration_ms"])
                if type(row["complete"]) is not bool or row["reason"] not in (
                        "duration", "disconnect", "connection", "subscription", "transport", "limit", "interrupted"):
                    raise ValueError("Invalid capture completion metadata")
                if row["records"] != count or row["elapsed_ms"] < previous:
                    raise ValueError("Capture counts or timing do not match observations")
                if row["complete"] != (row["reason"] == "duration"):
                    raise ValueError("Inconsistent capture completion metadata")
                if row["complete"] and row["elapsed_ms"] < start["duration_ms"]:
                    raise ValueError("Capture ended before its requested duration")
                end = row
                continue
            validate_record(row)
            if row["elapsed_ms"] < previous or row["elapsed_ms"] >= start["duration_ms"]:
                raise ValueError("Observation timestamps must be monotonic and inside capture duration")
            previous = row["elapsed_ms"]
            count += 1
            if row.get("retained", False):
                retained += 1
            else:
                records.append(row)
    if start is None or end is None:
        raise ValueError("Incomplete evidence file: header and footer are required")
    capture = dict(end, source=start["source"], duration_ms=start["duration_ms"])
    capture["retained"] += retained
    return {"records": records, "capture": capture}
