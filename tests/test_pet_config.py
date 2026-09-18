"""Fictional private-configuration contract; no Home Assistant dependency."""
import copy
import unittest

from custom_components.espresense_pet.config import validate_config


def example_config():
    return {"schema": 1, "pet_id": "example_pet", "name": "Example Pet", "device_alias": "example-collar",
            "nodes": {"node_a": {"mqtt_room": "example-a", "room": "room_a"},
                      "node_b": {"mqtt_room": "example-b", "room": "room_b"}},
            "doors": {"entry": {"contact": "binary_sensor.example_entry", "nodes": ["node_a"],
                                 "exterior": True, "camera": "example-camera",
                                 "inside_zones": ["threshold"], "outside_zones": ["walkway"]},
                      "back": {"contact": "binary_sensor.example_back", "nodes": ["node_b"],
                                "exterior": True, "camera": "example-camera",
                                "inside_zones": ["back_threshold"], "outside_zones": ["back_walkway"]}}}


class PetConfigTests(unittest.TestCase):
    def test_defaults_are_normalized_without_mutating_the_source(self):
        raw = example_config()
        original = copy.deepcopy(raw)
        normalized = validate_config(raw)
        self.assertEqual(raw, original)
        self.assertEqual(normalized["timing"]["observation_fresh_s"], 20)
        self.assertEqual(normalized["timing"]["health_silence_s"], 1800)
        self.assertEqual(normalized["doors"]["entry"]["near_rssi_dbm"], -65)
        self.assertEqual(normalized["frigate_topic"], "frigate/events")
        normalized["doors"]["entry"]["nodes"].append("node_b")
        self.assertEqual(raw["doors"]["entry"]["nodes"], ["node_a"])

    def test_rejects_invalid_fields_and_selectors_without_echoing_values(self):
        mutations = [lambda c: c.update(unknown="sensitive-marker"),
                     lambda c: c.update(schema=True), lambda c: c.update(schema=2),
                     lambda c: c.update(device_alias="irk:sensitive-marker"),
                     lambda c: c.update(device_alias="aabbccddeeff"),
                     lambda c: c.update(device_alias="aa-bb-cc-dd-ee-ff"),
                     lambda c: c.update(device_alias="secret/#"),
                     lambda c: c.update(name="bad\nname"),
                     lambda c: c.update(pet_id="bad-id"),
                     lambda c: c.update(frigate_topic="frigate/#"),
                     lambda c: c["nodes"]["node_a"].update(ip="sensitive-marker"),
                     lambda c: c["doors"]["entry"].update(contact="switch.example_entry"),
                     lambda c: c["doors"]["entry"].update(exterior=1),
                     lambda c: c["doors"]["entry"].update(near_rssi_dbm=True),
                     lambda c: c["doors"]["entry"].update(near_rssi_dbm=float("nan"))]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                raw = example_config()
                mutate(raw)
                with self.assertRaises(ValueError) as error:
                    validate_config(raw)
                self.assertNotIn("sensitive-marker", str(error.exception))

    def test_rejects_ambiguous_maps_and_unbounded_collections(self):
        mutations = [lambda c: c.update(nodes={}), lambda c: c.update(doors={}),
                     lambda c: c["nodes"]["node_b"].update(mqtt_room="example-a"),
                     lambda c: c["doors"]["back"].update(contact="binary_sensor.example_entry"),
                     lambda c: c["doors"]["entry"].update(nodes=["missing"]),
                     lambda c: c["doors"]["entry"].update(nodes=["node_a", "node_a"]),
                     lambda c: c["doors"]["entry"].update(inside_zones=["threshold", "threshold"]),
                     lambda c: c["doors"]["entry"].update(outside_zones=["threshold"]),
                     lambda c: c["doors"]["entry"].update(camera=None),
                     lambda c: c.update(doors={"door_" + str(i): {} for i in range(17)})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                raw = example_config()
                mutate(raw)
                with self.assertRaises(ValueError):
                    validate_config(raw)

    def test_timing_bounds_reject_huge_numbers_and_booleans(self):
        for value in (0, -1, True, float("nan"), float("inf"), 10 ** 400, "20"):
            raw = example_config()
            raw["timing"] = {"room_hold_s": value}
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                validate_config(raw)
        raw = example_config()
        raw["timing"] = {"invented_timer": 20}
        with self.assertRaises(ValueError):
            validate_config(raw)

    def test_internal_door_without_camera_is_supported(self):
        raw = example_config()
        raw["doors"] = {"inside": {"contact": "binary_sensor.example_internal", "nodes": ["node_a"], "exterior": False}}
        normalized = validate_config(raw)
        self.assertIsNone(normalized["doors"]["inside"]["camera"])
        self.assertEqual(normalized["doors"]["inside"]["outside_zones"], [])

    def test_door_ids_use_entity_safe_underscores_without_normalization_collisions(self):
        raw = example_config()
        raw["doors"]["entry-door"] = raw["doors"].pop("entry")
        with self.assertRaises(ValueError):
            validate_config(raw)


if __name__ == "__main__":
    unittest.main()
