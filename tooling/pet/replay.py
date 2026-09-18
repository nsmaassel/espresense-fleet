"""Bounded normalized-event replay using the exact integration engine."""
import json
import math
from pathlib import Path

from custom_components.espresense_pet.config import validate_config
from custom_components.espresense_pet.engine import Engine


def parse_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Invalid JSON input") from None


def read_config(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Configuration too large")
    return validate_config(parse_json(path.read_text(encoding="utf-8")))


def read_events(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Replay too large")
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index >= 10000 or len(line) > 8192:
                raise ValueError("Replay limit exceeded")
            yield parse_json(line)


FIELDS = {
    "transport": {"connected"}, "observation": {"node", "distance_m"},
    "door_open": {"door"}, "camera": {"door", "zone", "event_id", "evidence_at_s"},
    "acknowledge": set(), "tick": set(), "restart": set(),
}


def validate_event(row, previous):
    if not isinstance(row, dict) or not isinstance(row.get("kind"), str):
        raise ValueError("Invalid replay event")
    kind = row["kind"]
    if kind not in FIELDS:
        raise ValueError("Unsupported replay event")
    required = {"schema", "kind", "elapsed_s"} | FIELDS[kind]
    optional = {"retained"} if kind in ("observation", "camera") else set()
    if kind == "observation":
        optional.add("rssi_dbm")
    if not required <= row.keys() or row.keys() - required - optional:
        raise ValueError("Invalid replay fields")
    if type(row["schema"]) is not int or row["schema"] != 1:
        raise ValueError("Unsupported replay schema")
    elapsed = row["elapsed_s"]
    if (type(elapsed) not in (int, float) or not previous <= elapsed <= 86400
            or not math.isfinite(elapsed)):
        raise ValueError("Replay time must be ordered within one day")
    if "retained" in row and type(row["retained"]) is not bool:
        raise ValueError("Invalid retained flag")
    if kind == "transport" and type(row["connected"]) is not bool:
        raise ValueError("Invalid transport flag")
    return elapsed


def replay(config, events):
    engine = Engine(config)
    snapshots, previous = [], 0
    for row in events:
        now = validate_event(row, previous)
        previous, kind = now, row["kind"]
        if kind == "restart":
            engine = Engine(config, restored=engine.dump())
            intents = []
        elif row.get("retained", False):
            intents = engine.advance(now)
        elif kind == "transport":
            intents = engine.transport(row["connected"], now)
        elif kind == "observation":
            intents = engine.observe(row["node"], row["distance_m"], row.get("rssi_dbm"), now)
        elif kind == "door_open":
            intents = engine.door_open(row["door"], now)
        elif kind == "camera":
            intents = engine.camera(row["door"], row["zone"], row["event_id"], row["evidence_at_s"], now)
        elif kind == "acknowledge":
            intents = engine.acknowledge(now)
        else:
            intents = engine.advance(now)
        snapshots.append({"elapsed_s": now, "event": kind, "state": engine.snapshot(now), "intents": intents})
    if not snapshots:
        raise ValueError("Replay requires events")
    return {"schema": 1, "engine_version": "1.0", "snapshots": snapshots,
            "limitations": "Synthetic replay proves software behavior, not physical containment or alert delivery."}
