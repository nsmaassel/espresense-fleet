"""Pure injected-time advisory state machine. No network, HA or output actions."""
from collections import OrderedDict
import copy
import hashlib
import json
import re

from .config import fields, finite, validate_config
from .presence import Presence

LEVELS = {"clear": 0, "suspected": 1, "urgent": 2}
DEDUPE_LIMIT = 256


def clear_alert():
    return {"level": "clear", "door": None, "doors": [], "acknowledged": False}


def intent(level, door, reason):
    return {"level": level, "door": door, "reason": reason}


class Engine:
    def __init__(self, config, restored=None):
        self.config = validate_config(config)
        self.timing = self.config["timing"]
        self.presence = Presence(self.config)
        self._now = 0
        self.connected = False
        self.monitored_since = None
        self.alert = clear_alert()
        self.incident_since = None
        self.openings, self.heads_up = {}, {}
        self.camera_seen = OrderedDict()
        self.recovery_room = self.recovery_since = self.recovery_last = None
        self.recovery_cutoff = None
        self.health_notified = False
        if restored is not None:
            self._restore(restored)

    def _restore(self, stored):
        fields(stored, ("schema", "pet_id", "alert", "camera_seen"))
        if type(stored["schema"]) is not int or stored["schema"] != 1 or stored["pet_id"] != self.config["pet_id"]:
            raise ValueError("Stored incident identity or schema does not match")
        alert = stored["alert"]
        fields(alert, ("level", "door", "doors", "acknowledged"))
        if not isinstance(alert["level"], str) or alert["level"] not in LEVELS or type(alert["acknowledged"]) is not bool:
            raise ValueError("Invalid stored incident state")
        doors = alert["doors"]
        if not isinstance(doors, list) or len(doors) > 16:
            raise ValueError("Invalid stored incident doors")
        if any(not isinstance(door, str) or door not in self.config["doors"]
               or not self.config["doors"][door]["exterior"] for door in doors) or len(set(doors)) != len(doors):
            raise ValueError("Invalid stored incident doors")
        if alert["level"] == "clear":
            if alert != clear_alert():
                raise ValueError("Clear stored state cannot retain incident attributes")
        elif not isinstance(alert["door"], str) or alert["door"] not in doors:
            raise ValueError("Stored incident origin must be an affected door")
        seen = stored["camera_seen"]
        if (not isinstance(seen, list) or len(seen) > DEDUPE_LIMIT
                or any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) for key in seen)
                or len(set(seen)) != len(seen)):
            raise ValueError("Invalid stored camera deduplication state")
        self.alert = copy.deepcopy(alert)
        self.camera_seen = OrderedDict.fromkeys(seen)

    def _time(self, now):
        finite(now, 0, 1e15)
        if now < self._now:
            raise ValueError("Receipt time must be monotonic")

    def _door(self, door):
        if not isinstance(door, str) or door not in self.config["doors"]:
            raise ValueError("Door is not configured")

    def _reset_recovery(self):
        self.recovery_room = self.recovery_since = self.recovery_last = None

    def _move(self, now):
        self._now = now
        self.presence.expire(now)
        if (self.recovery_last is not None
                and (now - self.recovery_last > self.timing["observation_fresh_s"]
                     or self.presence.winner(now)[0] != self.recovery_room)):
            self._reset_recovery()

    def _silence_anchor(self):
        return max(value for value in (self.monitored_since, self.presence.last_seen) if value is not None)

    def _evaluate(self, now):
        results = []
        if not self.connected:
            return results
        if self.alert["level"] == "suspected":
            anchor = max(self._silence_anchor(), self.incident_since or 0)
            if now - anchor >= self.timing["urgent_silence_s"]:
                results.extend(self._raise("urgent", self.alert["door"], "monitored_indoor_silence", now))
        if now - self._silence_anchor() >= self.timing["health_silence_s"] and not self.health_notified:
            self.health_notified = True
            results.append(intent("health", None, "device_silence"))
        return results

    def _raise(self, level, door, reason, now):
        self._reset_recovery()
        if door not in self.alert["doors"]:
            self.alert["doors"].append(door)
            self.alert["doors"].sort()
        if LEVELS[level] <= LEVELS[self.alert["level"]]:
            return []
        if self.alert["level"] == "clear":
            self.incident_since = now
        self.alert.update(level=level, door=door, acknowledged=False)
        return [intent(level, door, reason)]

    def transport(self, connected, now):
        if type(connected) is not bool:
            raise ValueError("Transport state must be boolean")
        self._time(now)
        self._move(now)
        if self.connected != connected:
            self.connected = connected
            self.monitored_since = now if connected else None
            self.presence.disconnect()
            self._reset_recovery()
            self.health_notified = False
        return self._evaluate(now)

    def observe(self, node, distance_m, rssi_dbm_or_None, now):
        if not isinstance(node, str) or node not in self.config["nodes"]:
            raise ValueError("Observation node is not configured")
        finite(distance_m, 0, 10_000)
        if rssi_dbm_or_None is not None:
            finite(rssi_dbm_or_None, -200, 0)
        self._time(now)
        self._move(now)
        if not self.connected:
            return []
        room, evidence_at = self.presence.observe(node, distance_m, rssi_dbm_or_None, now)
        self.health_notified = False
        results = []
        if self.alert["level"] != "clear":
            if room is None or (self.recovery_room is not None and room != self.recovery_room):
                self._reset_recovery()
            if room is not None and evidence_at == now:
                if self.recovery_room is None:
                    self.recovery_room, self.recovery_since = room, now
                self.recovery_last = now
                if now - self.recovery_since >= self.timing["stable_clear_s"] and self.presence.room(now) == room:
                    door = self.alert["door"]
                    self.alert = clear_alert()
                    self.incident_since = None
                    self.recovery_cutoff = now
                    self._reset_recovery()
                    results.append(intent("recovered", door, "continuing_indoor_evidence"))
        return results + self._evaluate(now)

    def door_open(self, door, now):
        self._door(door)
        self._time(now)
        self._move(now)
        results = []
        if self.config["doors"][door]["exterior"]:
            self.openings[door] = now
            previous = self.heads_up.get(door)
            if (self.connected and self.presence.near(door, now) is True
                    and (previous is None or now - previous >= self.timing["heads_up_cooldown_s"])):
                self.heads_up[door] = now
                results.append(intent("heads_up", door, "door_open_while_near"))
        return results + self._evaluate(now)

    def camera(self, door, zone, event_id, evidence_at, now):
        self._door(door)
        if zone not in ("inside", "outside"):
            raise ValueError("Camera evidence must use a mapped inside or outside zone")
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", event_id):
            raise ValueError("Camera event ID is invalid")
        finite(evidence_at, 0, 1e15)
        self._time(now)
        self._move(now)
        definition = self.config["doors"][door]
        opening = self.openings.get(door)
        if (not definition["exterior"] or definition["camera"] is None or not definition[zone + "_zones"]
                or opening is None or not opening <= evidence_at <= now
                or evidence_at - opening > self.timing["correlation_s"]
                or now - evidence_at > self.timing["correlation_s"]
                or self.recovery_cutoff is not None and evidence_at <= self.recovery_cutoff):
            return self._evaluate(now)
        key = hashlib.sha256(json.dumps([door, event_id, zone], separators=(",", ":")).encode()).hexdigest()
        if key in self.camera_seen:
            return self._evaluate(now)
        self.camera_seen[key] = None
        if len(self.camera_seen) > DEDUPE_LIMIT:
            self.camera_seen.popitem(last=False)
        level = "urgent" if zone == "outside" else "suspected"
        return self._raise(level, door, "camera_" + zone, now) + self._evaluate(now)

    def acknowledge(self, now):
        self._time(now)
        self._move(now)
        if self.alert["level"] != "clear":
            self.alert["acknowledged"] = True
        return self._evaluate(now)

    def advance(self, now):
        self._time(now)
        self._move(now)
        return self._evaluate(now)

    def snapshot(self, now):
        self._time(now)
        last_seen = self.presence.last_seen
        if not self.connected:
            health = "transport_unavailable"
        elif now - self._silence_anchor() >= self.timing["health_silence_s"]:
            health = "device_silence"
        else:
            health = "never_seen" if last_seen is None else "ok"
        doors = {}
        for door in self.config["doors"]:
            near = self.presence.near(door, now) if self.connected else None
            light = "red" if door in self.alert["doors"] else "unknown" if near is None else "blue" if near else "off"
            doors[door] = {"near": near, "light": light}
        return {"pet_id": self.config["pet_id"], "room": self.presence.room(now) if self.connected else None,
                "last_room": self.presence.last_room(now), "recently_seen": last_seen is not None and now - last_seen <= self.timing["indoor_recent_s"],
                "last_seen_age_s": now - last_seen if last_seen is not None else None,
                "alert": copy.deepcopy(self.alert), "health": health, "doors": doors}

    def dump(self):
        return {"schema": 1, "pet_id": self.config["pet_id"], "alert": copy.deepcopy(self.alert),
                "camera_seen": list(self.camera_seen)}
