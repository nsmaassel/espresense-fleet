import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from tooling.pet.package import build_package

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "examples/pet.example.json").read_text())
        self.bindings = {"schema": 1, "notifications": {"urgent": "script.example_urgent"},
                         "lights": {"entry": {"light_entity": "light.example_entry",
                                               "preset_entity": "select.example_entry_preset",
                                               "off": "Off", "blue": "Blue breathe", "red": "Red blink"}}}

    def test_outputs_start_disabled_and_use_only_bound_scripts_and_presets(self):
        package = build_package(self.config, self.bindings)
        self.assertFalse(package["input_boolean"]["example_pet_outputs_enabled"]["initial"])
        self.assertEqual(package["espresense_pet"]["pet_id"], "example_pet")
        self.assertEqual(package["script"]["example_pet_acknowledge"]["sequence"],
                         [{"action": "espresense_pet.acknowledge"}])
        notification = next(a for a in package["automation"] if a["id"].endswith("notifications"))
        self.assertEqual(notification["triggers"][0]["event_data"], {"pet_id": "example_pet"})
        self.assertEqual(notification["actions"][0]["state"], "on")
        choices = notification["actions"][2]["choose"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]["sequence"][0]["target"]["entity_id"], "script.example_urgent")
        self.assertIn("camera_reference", choices[0]["sequence"][0]["data"]["variables"])
        lights = next(a for a in package["automation"] if a["id"].endswith("light_entry"))
        self.assertEqual(lights["actions"][0]["state"], "on")
        choices = lights["actions"][2]["choose"]
        self.assertEqual([c["conditions"][0]["state"] for c in choices], ["off", "blue", "red"])
        self.assertEqual(choices[0]["sequence"][2:], [{"action": "select.select_option",
                         "target": {"entity_id": "select.example_entry_preset"}, "data": {"option": "Off"}}])
        self.assertEqual(choices[1]["sequence"][2], {"action": "light.turn_on", "target": {"entity_id": "light.example_entry"}})

    def test_no_binding_generates_no_external_output_automations(self):
        package = build_package(self.config, {"schema": 1})
        self.assertNotIn("automation", package)

    def test_invalid_binding_cannot_inject_templates_or_arbitrary_actions(self):
        bad = [dict(schema=True), dict(schema=1, notifications={"urgent": "notify.example"}),
               dict(schema=1, notifications={"unknown": "script.example"}),
               dict(schema=1, lights={"not_a_door": self.bindings["lights"]["entry"]})]
        for key, value in (("red", "{{ states('sensor.private') }}"), ("light_entity", "script.example"),
                           ("preset_entity", "select.bad/path"), ("off", "")):
            entry = copy.deepcopy(self.bindings)
            entry["lights"]["entry"][key] = value
            bad.append(entry)
        for bindings in bad:
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                build_package(self.config, bindings)

    def test_actual_cli_writes_deterministic_private_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bindings.json").write_text(json.dumps(self.bindings))
            output = root / "package.yaml"
            args = [sys.executable, "-m", "tooling.pet", "package", "--config", "examples/pet.example.json",
                    "--bindings", str(root / "bindings.json"), "--output", str(output)]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = output.read_bytes()
            self.assertEqual(yaml.safe_load(original), build_package(self.config, self.bindings))
            self.assertEqual(subprocess.run(args, cwd=ROOT, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), original)
            args[-1] = str(root / "bindings.json")
            refused = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(json.loads((root / "bindings.json").read_text()), self.bindings)


if __name__ == "__main__":
    unittest.main()
