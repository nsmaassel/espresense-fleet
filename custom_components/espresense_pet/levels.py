"""Graded per-door proximity levels. Pure: no clock, network, HA or I/O.

A level names the evidence that raises it and how long that evidence holds it:
either a reading at or above `rssi_dbm` from one of its `nodes`, or the engine's
currently qualified `room`. Levels are listed strongest first; the strongest one
still inside its hold wins, and it steps down as holds lapse. Evidence is receipt
time only, never persisted, and is dropped whenever transport connectivity changes.
Configuration is validated by config.validate_levels.
"""


class DoorLevels:
    """When each of one door's levels last had qualifying evidence."""

    def __init__(self, levels):
        self.levels = levels
        self.seen = [None] * len(levels)

    def reading(self, node, rssi, now):
        if rssi is None:
            return
        for index, level in enumerate(self.levels):
            if node in level.get("nodes", ()) and rssi >= level["rssi_dbm"]:
                self.seen[index] = now

    def room(self, room, now):
        for index, level in enumerate(self.levels):
            if level.get("room") == room:
                self.seen[index] = now

    def forget(self):
        self.seen = [None] * len(self.levels)

    def active(self, now):
        for level, seen in zip(self.levels, self.seen):
            if seen is not None and now - seen < level["hold_s"]:
                return level["name"]
        return None
