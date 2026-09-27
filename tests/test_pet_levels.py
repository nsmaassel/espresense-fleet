"""Graded per-door proximity levels: config contract and injected-time engine behavior."""
import unittest

from custom_components.espresense_pet.config import validate_config
from custom_components.espresense_pet.engine import Engine
from test_pet_config import example_config


def levels_config():
    raw = example_config()
    raw["doors"]["entry"]["levels"] = [
        {"name": "close", "hold_s": 5, "nodes": ["node_a"], "rssi_dbm": -55},
        {"name": "near", "hold_s": 10, "nodes": ["node_a"], "rssi_dbm": -70},
        {"name": "next_room", "hold_s": 20, "room": "room_b"}]
    return raw


def engine(raw=None):
    result = Engine(raw or levels_config())
    result.transport(True, 0)
    return result


def level(result, now, door="entry"):
    return result.snapshot(now)["doors"][door]["level"]


class PetLevelConfigTests(unittest.TestCase):
    def test_levels_are_optional_and_accepted_when_valid(self):
        self.assertNotIn("levels", validate_config(example_config())["doors"]["entry"])
        normalized = validate_config(levels_config())
        self.assertEqual([item["name"] for item in normalized["doors"]["entry"]["levels"]],
                         ["close", "near", "next_room"])
        raw = levels_config()
        # Level nodes may be any configured node, not only the door's own.
        raw["doors"]["entry"]["levels"][0]["nodes"] = ["node_b", "node_a"]
        raw["doors"]["entry"]["levels"][0]["hold_s"] = 120
        raw["doors"]["entry"]["levels"][0]["rssi_dbm"] = 0
        validate_config(raw)
        # A validated config validates again unchanged, as the engine re-checks it.
        self.assertEqual(validate_config(validate_config(raw)), validate_config(raw))

    def test_rejects_invalid_levels(self):
        def entry(c):
            return c["doors"]["entry"]["levels"]

        mutations = [
            lambda c: c["doors"]["entry"].update(levels=[]),
            lambda c: c["doors"]["entry"].update(levels={"close": {}}),
            lambda c: entry(c).extend({"name": f"extra_{i}", "hold_s": 5, "room": "room_a"} for i in range(4)),
            lambda c: entry(c).append("close"),
            lambda c: entry(c)[0].update(unknown="sensitive-marker"),
            lambda c: entry(c)[0].pop("rssi_dbm"),
            lambda c: entry(c)[0].pop("hold_s"),
            lambda c: entry(c)[2].update(nodes=["node_a"]),
            lambda c: entry(c)[2].update(rssi_dbm=-50),
            lambda c: entry(c)[0].update(nodes=[]),
            lambda c: entry(c)[0].update(nodes="node_a"),
            lambda c: entry(c)[0].update(nodes=["node_a", "node_a"]),
            lambda c: entry(c)[0].update(nodes=["missing"]),
            lambda c: entry(c)[0].update(nodes=[["node_a"]]),
            lambda c: entry(c)[0].update(rssi_dbm=1),
            lambda c: entry(c)[0].update(rssi_dbm=-201),
            lambda c: entry(c)[0].update(rssi_dbm=True),
            lambda c: entry(c)[0].update(rssi_dbm=float("nan")),
            lambda c: entry(c)[0].update(hold_s=0),
            lambda c: entry(c)[0].update(hold_s=-1),
            lambda c: entry(c)[0].update(hold_s=120.5),
            lambda c: entry(c)[0].update(hold_s=float("inf")),
            lambda c: entry(c)[0].update(hold_s="5"),
            lambda c: entry(c)[2].update(room="missing_room"),
            lambda c: entry(c)[2].update(room=["room_b"]),
            lambda c: entry(c)[1].update(name="close"),
            lambda c: entry(c)[0].update(name="off"),
            lambda c: entry(c)[0].update(name="escape"),
            lambda c: entry(c)[0].update(name="unknown"),
            lambda c: entry(c)[0].update(name="Close"),
            lambda c: entry(c)[0].update(name="very-close"),
            lambda c: entry(c)[0].update(name="irk_sensitive_marker"),
            lambda c: entry(c)[0].update(name=None)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                raw = levels_config()
                mutate(raw)
                with self.assertRaises(ValueError) as error:
                    validate_config(raw)
                self.assertNotIn("sensitive-marker", str(error.exception))


class PetLevelEngineTests(unittest.TestCase):
    def test_strongest_active_level_wins_and_steps_down_as_holds_lapse(self):
        result = engine()
        self.assertEqual(level(result, 0), "off")
        result.observe("node_a", 1, -50, 1)
        self.assertEqual(level(result, 1), "close")
        self.assertEqual(level(result, 5.99), "close")
        self.assertEqual(level(result, 6), "near")
        self.assertEqual(level(result, 10.99), "near")
        self.assertEqual(level(result, 11), "off")

    def test_weaker_reading_does_not_hide_a_still_held_stronger_level(self):
        result = engine()
        result.observe("node_a", 1, -50, 1)
        result.observe("node_a", 1, -65, 3)
        self.assertEqual(level(result, 3), "close")
        self.assertEqual(level(result, 6), "near")
        self.assertEqual(level(result, 12.99), "near")
        self.assertEqual(level(result, 13), "off")

    def test_rssi_threshold_is_inclusive(self):
        result = engine()
        result.observe("node_a", 1, -55, 1)
        self.assertEqual(level(result, 1), "close")
        result = engine()
        result.observe("node_a", 1, -55.01, 1)
        self.assertEqual(level(result, 1), "near")
        result = engine()
        result.observe("node_a", 1, -70.01, 1)
        self.assertEqual(level(result, 1), "off")

    def test_missing_rssi_and_unlisted_nodes_raise_no_node_level(self):
        result = engine()
        result.observe("node_a", 1, None, 1)
        result.observe("node_b", 2, -30, 2)
        self.assertEqual(level(result, 2), "off")

    def test_room_level_needs_the_qualified_room_and_holds_from_last_room_evidence(self):
        result = engine()
        for now in (0, 15):
            result.observe("node_b", 1, -80, now)
            self.assertEqual(level(result, now), "off")
        result.observe("node_b", 1, -80, 30)
        self.assertEqual(result.snapshot(30)["room"], "room_b")
        self.assertEqual(level(result, 30), "next_room")
        self.assertEqual(level(result, 49.99), "next_room")
        self.assertEqual(level(result, 50), "off")

    def test_other_room_does_not_raise_a_room_level(self):
        result = engine()
        for now in (0, 15, 30):
            result.observe("node_a", 1, -90, now)
        self.assertEqual(result.snapshot(30)["room"], "room_a")
        self.assertEqual(level(result, 30), "off")

    def test_transport_change_clears_evidence_and_reports_unknown_while_disconnected(self):
        result = engine()
        result.observe("node_a", 1, -50, 1)
        result.transport(False, 2)
        self.assertEqual(level(result, 2), "unknown")
        result.observe("node_a", 1, -50, 3)
        result.transport(True, 4)
        # A blip inside the old hold must not revive the level.
        self.assertEqual(level(result, 4), "off")
        result.observe("node_a", 1, -50, 5)
        self.assertEqual(level(result, 5), "close")

    def test_repeated_connected_state_keeps_evidence(self):
        result = engine()
        result.observe("node_a", 1, -50, 1)
        result.transport(True, 2)
        self.assertEqual(level(result, 2), "close")

    def test_escape_outranks_every_level(self):
        result = engine()
        result.observe("node_a", 1, -50, 0)
        result.door_open("entry", 1)
        result.camera("entry", "inside", "example-event", 2, 2)
        result.observe("node_a", 1, -50, 3)
        self.assertEqual(level(result, 3), "escape")
        result.transport(False, 4)
        self.assertEqual(level(result, 4), "escape")

    def test_door_without_levels_reports_only_off_unknown_or_escape(self):
        result = engine()
        result.observe("node_b", 1, -30, 1)
        self.assertEqual(level(result, 1, "back"), "off")
        result.transport(False, 2)
        self.assertEqual(level(result, 2, "back"), "unknown")
        result = engine(example_config())
        result.observe("node_a", 1, -30, 0)
        self.assertEqual(level(result, 0), "off")
        self.assertEqual(result.snapshot(0)["doors"]["entry"]["light"], "blue")
        result.door_open("entry", 1)
        result.camera("entry", "outside", "example-event", 2, 2)
        self.assertEqual(level(result, 2), "escape")

    def test_dump_and_restore_do_not_carry_level_evidence(self):
        result = engine()
        result.observe("node_a", 1, -50, 1)
        stored = result.dump()
        self.assertEqual(set(stored), {"schema", "pet_id", "alert", "camera_seen"})
        restored = Engine(levels_config(), stored)
        restored.transport(True, 2)
        self.assertEqual(level(restored, 2), "off")


if __name__ == "__main__":
    unittest.main()
