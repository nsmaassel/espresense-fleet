"""Bounded receipt evidence and room continuity, independent of incident policy."""


class Presence:
    def __init__(self, config):
        self.config = config
        self.timing = config["timing"]
        self.observations = {}
        self.last_seen = None
        self.candidate = self.candidate_since = self.candidate_last = None
        # Current qualification must be earned again after interrupted evidence;
        # accepted/qualified_at below are only the separately retained history.
        self.qualified_room = None
        self.accepted = self.qualified_at = None

    def disconnect(self):
        self.observations.clear()
        self.candidate = self.candidate_since = self.candidate_last = None
        self.qualified_room = None

    def expire(self, now):
        fresh = self.timing["observation_fresh_s"]
        self.observations = {node: observation for node, observation in self.observations.items()
                             if now - observation[2] <= fresh}
        if self.candidate_last is not None and now - self.candidate_last > fresh:
            self.candidate = self.candidate_since = self.candidate_last = None
            self.qualified_room = None
        if self.qualified_at is not None and now - self.qualified_at > self.timing["last_room_retention_s"]:
            self.accepted = self.qualified_at = None

    def winner(self, now):
        current = {node: data for node, data in self.observations.items()
                   if now - data[2] <= self.timing["observation_fresh_s"]}
        if not current:
            return None, None
        nearest = min(data[0] for data in current.values())
        winners = {node: data for node, data in current.items() if data[0] == nearest}
        rooms = {self.config["nodes"][node]["room"] for node in winners}
        if len(rooms) != 1:
            return None, None
        return next(iter(rooms)), max(data[2] for data in winners.values())

    def observe(self, node, distance, rssi, now):
        self.expire(now)
        self.observations[node] = (distance, rssi, now)
        self.last_seen = now
        room, evidence_at = self.winner(now)
        if room is None:
            self.candidate = self.candidate_since = self.candidate_last = None
            self.qualified_room = None
            return room, evidence_at
        if room != self.candidate:
            self.candidate, self.candidate_since = room, now
            self.qualified_room = None
        self.candidate_last = evidence_at
        if evidence_at == now:
            if now - self.candidate_since >= self.timing["room_hold_s"]:
                self.qualified_room = room
                self.accepted = room
            if self.qualified_room == room:
                self.qualified_at = now
        return room, evidence_at

    def last_room(self, now):
        if self.qualified_at is None or now - self.qualified_at > self.timing["last_room_retention_s"]:
            return None
        return self.accepted

    def room(self, now):
        room, _ = self.winner(now)
        return room if room == self.qualified_room else None

    def near(self, door, now):
        definition = self.config["doors"][door]
        rssis = [self.observations[node][1] for node in definition["nodes"]
                 if node in self.observations and self.observations[node][1] is not None
                 and now - self.observations[node][2] <= self.timing["observation_fresh_s"]]
        return any(rssi >= definition["near_rssi_dbm"] for rssi in rssis) if rssis else None
