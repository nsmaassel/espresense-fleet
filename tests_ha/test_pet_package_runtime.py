"""Load the generated package in real HA and exercise its action guards."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant import bootstrap, config as ha_config, loader
from homeassistant.core import HomeAssistant, callback

from tooling.pet.package import build_package

ROOT = Path(__file__).resolve().parents[1]


class PackageRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_package_loads_and_only_enabled_bound_outputs_run(self):
        with tempfile.TemporaryDirectory() as directory:
            shutil.copytree(ROOT / "custom_components" / "espresense_pet",
                            Path(directory) / "custom_components" / "espresense_pet",
                            ignore=shutil.ignore_patterns("__pycache__"))
            hass = HomeAssistant(directory)
            loader.async_setup(hass)
            calls = []
            self.disable_during_light = False

            async def record(call):
                calls.append((call.domain, call.service, dict(call.data)))
                if self.disable_during_light and call.domain == "light":
                    await hass.services.async_call("input_boolean", "turn_off", {
                        "entity_id": "input_boolean.example_pet_outputs_enabled"}, blocking=True)

            @callback
            def status(hass, listener):
                return lambda: None

            async def subscribe(*args, **kwargs):
                return lambda: None

            config = json.loads((ROOT / "examples/pet.example.json").read_text())
            package = build_package(config, {"schema": 1, "notifications": {"urgent": "script.example_urgent"},
                                            "lights": {"entry": {"light_entity": "light.example_entry",
                                                "preset_entity": "select.example_entry_preset", "off": "Off",
                                                "blue": "Blue breathe", "red": "Red blink"}}})
            package["script"]["example_urgent"] = {"sequence": [{"action": "synthetic_capture.record", "data": {
                "level": "{{ level }}", "camera_reference": "{{ camera_reference }}"}}]}
            hass.services.async_register("synthetic_capture", "record", record)
            try:
                with patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new=AsyncMock(return_value=True)), \
                     patch("homeassistant.components.mqtt.async_subscribe_connection_status", new=status), \
                     patch("homeassistant.components.mqtt.is_connected", return_value=True), \
                     patch("homeassistant.components.mqtt.async_subscribe", new=subscribe):
                    full_config = {"homeassistant": {"name": "Synthetic test", "latitude": 0,
                        "longitude": 0, "elevation": 0, "unit_system": "metric", "time_zone": "UTC",
                        "packages": {"pet": package}}}
                    await ha_config.merge_packages_config(hass, full_config, {"pet": package})
                    await bootstrap.async_from_config_dict(full_config, hass)
                    await hass.async_start()
                    await hass.async_block_till_done()
                    self.assertTrue("espresense_pet" in hass.data)
                    enabled = "input_boolean.example_pet_outputs_enabled"
                    self.assertEqual(hass.states.get(enabled).state, "off")
                    self.assertEqual(len(hass.states.async_all("automation")), 2)
                    hass.services.async_register("light", "turn_on", record)
                    hass.services.async_register("select", "select_option", record)
                    event = {"pet_id": "example_pet", "level": "urgent", "door": "entry", "reason": "camera",
                             "camera_reference": {"camera": "example-camera", "event_id": "synthetic-event"}}
                    hass.bus.async_fire("espresense_pet_advisory", event)
                    await hass.async_block_till_done()
                    self.assertEqual(calls, [])
                    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": enabled}, blocking=True)
                    await hass.async_block_till_done()
                    self.assertEqual(calls, [])  # Unknown local evidence has no preset.
                    hass.bus.async_fire("espresense_pet_advisory", event)
                    await hass.async_block_till_done()
                    self.assertEqual(calls, [("synthetic_capture", "record", {
                        "level": "urgent", "camera_reference": event["camera_reference"]})])
                    calls.clear()
                    for intent, expected in (("blue", "Blue breathe"), ("red", "Red blink"), ("off", "Off")):
                        hass.states.async_set("sensor.example_pet_light_entry", intent)
                        await hass.async_block_till_done()
                        expected_calls = [] if intent == "off" else [("light", "turn_on", {"entity_id": ["light.example_entry"]})]
                        expected_calls.append(("select", "select_option", {"entity_id": ["select.example_entry_preset"], "option": expected}))
                        self.assertEqual(calls, expected_calls)
                        calls.clear()
                    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": enabled}, blocking=True)
                    hass.states.async_set("sensor.example_pet_light_entry", "red")
                    hass.bus.async_fire("espresense_pet_advisory", event)
                    await hass.async_block_till_done()
                    self.assertEqual(calls, [])
                    self.disable_during_light = True
                    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": enabled}, blocking=True)
                    await hass.async_block_till_done()
                    self.assertEqual(calls, [("light", "turn_on", {"entity_id": ["light.example_entry"]})])
                    self.assertEqual(hass.states.get(enabled).state, "off")
                    self.disable_during_light = False
                    hass.states.async_set("sensor.example_pet_light_entry", "unknown")
                    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": enabled}, blocking=True)
                    await hass.async_block_till_done()
                    calls.clear()
                    coordinator = hass.data["espresense_pet"]
                    with patch.object(coordinator.store, "async_save", new=AsyncMock(side_effect=OSError("synthetic failure"))):
                        coordinator.enqueue("door_open", ("entry",), coordinator.clock())
                        coordinator.enqueue("camera", ("entry", "outside", "unsaved-event", coordinator.clock()), coordinator.clock())
                        await coordinator.async_flush()
                        await hass.async_block_till_done()
                        self.assertEqual(hass.states.get("sensor.example_pet_alert").state, "urgent")
                        self.assertFalse(hass.states.get("sensor.example_pet_health").attributes["storage_ok"])
                        self.assertEqual(calls, [])  # Visible unsaved latch cannot deliver a preset or notification.
                    coordinator.enqueue("advance", (), coordinator.clock())
                    await coordinator.async_flush()
                    await hass.async_block_till_done()
                    self.assertTrue(hass.states.get("sensor.example_pet_health").attributes["storage_ok"])
                    self.assertIn(("select", "select_option", {"entity_id": ["select.example_entry_preset"], "option": "Red blink"}), calls)
                    self.assertTrue(any(domain == "synthetic_capture" for domain, _, _ in calls))
            finally:
                if "espresense_pet" in hass.data:
                    await hass.data["espresense_pet"].async_stop()
                await hass.async_stop()


if __name__ == "__main__":
    unittest.main()
