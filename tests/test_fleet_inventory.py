import unittest
from pathlib import Path
import tempfile

from tooling.fleet.inventory import InventoryError, load, resolve


class InventoryTests(unittest.TestCase):
    def inventory(self, **changes):
        return {"nodes": [{"id": "study", "address": "node.example", "room": "study"}], **changes}

    def test_precedence_and_unprovisioned_node(self):
        nodes = resolve(self.inventory(
            broker={"host": "broker.example", "port": 1883},
            defaults={"hardware": {"led_1_pin": 35}},
            nodes=[{"id": "study", "address": "node.example", "room": "study",
                    "settings": {"main": {"mqtt_port": 1884}}}, {"id": "spare"}],
        ))
        self.assertEqual(nodes[0].desired, {"hardware": {"led_1_pin": 35},
                         "main": {"room": "study", "mqtt_host": "broker.example", "mqtt_port": 1884}})
        self.assertIsNone(nodes[1].address)

    def test_rejects_invalid_inventory_before_network(self):
        bad = [
            self.inventory(extra=True), self.inventory(nodes=[]),
            self.inventory(nodes=[{"id": "same"}, {"id": "same"}]),
            self.inventory(nodes=[{"id": "one", "address": "NODE.example"},
                                  {"id": "two", "address": "node.example:80"}]),
            self.inventory(nodes=[{"id": "one", "address": "http://node.example"}]),
            self.inventory(nodes=[{"id": "one", "address": "999.2.3.4"}]),
            self.inventory(nodes=[{"id": "one", "address": "node.example:65536"}]),
            self.inventory(broker={"host": "broker.example", "port": True}),
            self.inventory(defaults={"bluetooth": {"x": 1}}),
            self.inventory(defaults={"main": {"x": [1]}}),
            self.inventory(defaults={"main": {"x": float("nan")}}),
            self.inventory(defaults={"main": {"mqtt_pass": "example"}}),
            self.inventory(defaults={"extras": {"filter": "irk:fictional"}}),
            self.inventory(defaults={"main": {"room": "\ud800"}}),
            self.inventory(defaults={"main": {"mqtt_port": 1.5}}, nodes=[{"id": "one", "settings": {"main": {"mqtt_port": 1883}}}]),
            self.inventory(defaults={"main": {"mqtt_host": "https://broker.example"}}, nodes=[{"id": "one", "settings": {"main": {"mqtt_host": "broker.example"}}}]),
            self.inventory(broker={"host": "broker.example"}, defaults={"main": {"mqtt_host": "other.example"}}),
            self.inventory(nodes=[{"id": "one", "room": "a", "settings": {"main": {"room": "b"}}}]),
        ]
        for fixture in bad:
            with self.subTest(fixture=fixture), self.assertRaises(InventoryError):
                resolve(fixture)

    def test_duplicate_yaml_keys_and_recursive_values_are_rejected(self):
        for content in ("nodes: []\nnodes: []", "nodes: &loop [*loop]", "nodes: [{id: okay, settings: {main: {room: &room [*room]}}}]"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "inventory.yaml"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(InventoryError):
                    load(path)

    def test_selection_validated_against_all_nodes(self):
        with self.assertRaises(InventoryError):
            resolve(self.inventory(), ["missing"])
        with self.assertRaises(InventoryError):
            resolve(self.inventory(nodes=[{"id": "study", "room": "study"}, {"id": "bad", "oops": 1}]), ["study"])

    def test_optional_metadata_and_unassigned_room_accept_null(self):
        nodes = resolve(self.inventory(nodes=[{"id": "spare", "mac": None, "room": None, "status": None}]))
        self.assertEqual(nodes[0].desired, {})

    def test_ipv6_broker_is_a_host_and_node_address_is_a_url_authority(self):
        nodes = resolve(self.inventory(broker={"host": "2001:db8::1"},
                                      nodes=[{"id": "study", "address": "[2001:db8::2]:8080", "room": "study"}]))
        self.assertEqual(nodes[0].address, "[2001:db8::2]:8080")
        self.assertEqual(nodes[0].desired["main"]["mqtt_host"], "2001:db8::1")


if __name__ == "__main__":
    unittest.main()
