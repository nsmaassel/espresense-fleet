"""Strict, dependency-free configuration for one subject's advisory engine."""
import copy
import math
import re

DEFAULT_TIMING = {"observation_fresh_s": 20, "room_hold_s": 30, "last_room_retention_s": 600,
                  "indoor_recent_s": 900, "correlation_s": 180, "stable_clear_s": 60,
                  "urgent_silence_s": 180, "health_silence_s": 1800, "heads_up_cooldown_s": 60}


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Missing or unsupported configuration fields")


def finite(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number in the supported range")
    if not low <= value <= high or not math.isfinite(value):
        raise ValueError("Expected a finite number in the supported range")
    return value


def alias(value, identifier=False):
    pattern = r"[a-z][a-z0-9_]{0,47}" if identifier else r"[a-z][a-z0-9_-]{0,47}"
    if (not isinstance(value, str) or not re.fullmatch(pattern, value)
            or value.startswith("irk") or re.fullmatch(r"[a-f0-9]{12,}", value)
            or re.fullmatch(r"(?:[a-f0-9]{2}-){5}[a-f0-9]{2}", value)):
        raise ValueError("Expected a friendly bounded alias, never a raw identifier or credential")
    return value


def aliases(value, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError("Alias collection has an invalid size")
    for item in value:
        alias(item)
    if len(value) != len(set(value)):
        raise ValueError("Duplicate aliases are not allowed")
    return value


def validate_config(raw):
    fields(raw, ("schema", "pet_id", "name", "device_alias", "nodes", "doors"), ("timing", "frigate_topic"))
    if type(raw["schema"]) is not int or raw["schema"] != 1:
        raise ValueError("Unsupported configuration schema")
    alias(raw["pet_id"], identifier=True)
    alias(raw["device_alias"])
    name = raw["name"]
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not name.strip() or not name.isprintable():
        raise ValueError("Display name must be short printable text")
    nodes, doors = raw["nodes"], raw["doors"]
    if not isinstance(nodes, dict) or not 1 <= len(nodes) <= 64:
        raise ValueError("Configure 1 to 64 nodes")
    slugs = set()
    for node, definition in nodes.items():
        alias(node)
        fields(definition, ("mqtt_room", "room"))
        alias(definition["room"])
        slug = alias(definition["mqtt_room"])
        if slug in slugs:
            raise ValueError("MQTT node mappings must be unique")
        slugs.add(slug)
    if not isinstance(doors, dict) or not 1 <= len(doors) <= 16:
        raise ValueError("Configure 1 to 16 doors")
    normalized = copy.deepcopy(raw)
    contacts = set()
    for door, definition in normalized["doors"].items():
        alias(door, identifier=True)
        fields(definition, ("contact", "nodes", "exterior"),
               ("near_rssi_dbm", "camera", "inside_zones", "outside_zones"))
        contact = definition["contact"]
        if not isinstance(contact, str) or not re.fullmatch(r"binary_sensor\.[a-z0-9_]{1,64}", contact):
            raise ValueError("Door contact must be a binary_sensor entity")
        if contact in contacts:
            raise ValueError("Door contacts must be unique")
        contacts.add(contact)
        aliases(definition["nodes"], 1, 64)
        if set(definition["nodes"]) - nodes.keys():
            raise ValueError("Door nodes must reference configured nodes")
        if type(definition["exterior"]) is not bool:
            raise ValueError("Exterior must be a boolean")
        definition.setdefault("near_rssi_dbm", -65)
        finite(definition["near_rssi_dbm"], -200, 0)
        definition.setdefault("camera", None)
        definition.setdefault("inside_zones", [])
        definition.setdefault("outside_zones", [])
        inside = aliases(definition["inside_zones"], 0, 16)
        outside = aliases(definition["outside_zones"], 0, 16)
        if set(inside) & set(outside):
            raise ValueError("Inside and outside zones must be disjoint")
        if definition["camera"] is None:
            if inside or outside:
                raise ValueError("Zone mappings require a camera")
        else:
            alias(definition["camera"])
            if not inside and not outside:
                raise ValueError("Camera mappings require at least one zone")
    timings = normalized.get("timing", {})
    fields(timings, (), DEFAULT_TIMING)
    normalized["timing"] = DEFAULT_TIMING | timings
    for value in normalized["timing"].values():
        finite(value, 0.1, 86_400)
    topic = normalized.setdefault("frigate_topic", "frigate/events")
    if (not isinstance(topic, str) or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", topic)
            or len(topic) > 128):
        raise ValueError("Frigate topic must be one bounded exact MQTT topic")
    return normalized
