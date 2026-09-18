"""Real HA 2026.9.2 lifecycle/entities/storage; only MQTT transport is stubbed."""
import asyncio
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant import bootstrap, loader
from homeassistant.core import HomeAssistant, callback
from homeassistant.setup import async_setup_component

from custom_components.espresense_pet.coordinator import DOMAIN, QUEUE_LIMIT, Coordinator

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    now = 1000.0

    def monotonic(self):
        return self.now

    def wall(self):
        return 1_000_000.0 + self.now


class PetRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        destination = Path(self.directory.name) / "custom_components" / DOMAIN
        shutil.copytree(ROOT / "custom_components" / DOMAIN, destination, ignore=shutil.ignore_patterns("__pycache__"))
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        await bootstrap.async_from_config_dict({"homeassistant": {"name": "Synthetic test", "latitude": 0,
                                                "longitude": 0, "elevation": 0, "unit_system": "metric",
                                                "time_zone": "UTC"}}, self.hass)
        self.clock = Clock()
        self.subscriptions, self.status_callbacks, self.lifecycle = {}, [], []
        self.removed = []
        self.config = json.loads((ROOT / "examples" / "pet.example.json").read_text())
        self.events = []
        self.hass.bus.async_listen("espresense_pet_advisory", self._advisory)

        @callback
        def status_listener(hass, listener):
            self.lifecycle.append("listener")
            self.status_callbacks.append(listener)
            return lambda: self.removed.append("status")

        @callback
        def connected(hass):
            self.lifecycle.append("snapshot")
            return self.initial_connected

        async def subscribe(hass, topic, listener, qos=0):
            self.subscriptions[topic] = listener
            return lambda: self.removed.append(topic)

        self.initial_connected = True
        self.patches = [patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new=AsyncMock(return_value=True)),
                        patch("homeassistant.components.mqtt.async_subscribe_connection_status", new=status_listener),
                        patch("homeassistant.components.mqtt.is_connected", new=connected),
                        patch("homeassistant.components.mqtt.async_subscribe", new=subscribe),
                        patch("custom_components.espresense_pet.coordinator.monotonic", new=self.clock.monotonic),
                        patch("custom_components.espresense_pet.coordinator.wall_time", new=self.clock.wall)]
        for replacement in self.patches:
            replacement.start()

    @callback
    def _advisory(self, event):
        self.events.append(dict(event.data))

    async def asyncTearDown(self):
        if DOMAIN in self.hass.data:
            await self.hass.data[DOMAIN].async_stop()
        await self.hass.async_stop()
        for replacement in reversed(self.patches):
            replacement.stop()
        self.directory.cleanup()

    async def start(self):
        self.assertTrue(await async_setup_component(self.hass, DOMAIN, {DOMAIN: self.config}))
        self.coordinator = self.hass.data[DOMAIN]
        await self.flush()

    async def flush(self):
        await self.hass.async_block_till_done()
        await self.coordinator.async_flush()
        await self.hass.async_block_till_done()

    async def observation(self, offset, *, retained=False):
        self.clock.now = 1000 + offset
        topic = "espresense/devices/example-collar/example-a"
        self.subscriptions[topic](SimpleNamespace(topic=topic, payload='{"distance":1,"rssi":-60}', retain=retained))
        await self.flush()

    async def open_door(self, offset):
        self.clock.now = 1000 + offset
        self.hass.states.async_set("binary_sensor.example_entry", "off")
        await self.flush()
        self.hass.states.async_set("binary_sensor.example_entry", "on")
        await self.flush()

    async def camera(self, offset, zone="threshold", event_id="synthetic-event"):
        self.clock.now = 1000 + offset
        payload = {"type": "new", "after": {"id": event_id, "label": "cat", "camera": "example-camera",
                   "false_positive": False, "end_time": None, "frame_time": self.clock.wall(), "current_zones": [zone]}}
        topic = "frigate/events"
        self.subscriptions[topic](SimpleNamespace(topic=topic, payload=json.dumps(payload), retain=False))
        await self.flush()

    async def test_real_entities_startup_order_retained_and_identical_receipts(self):
        await self.start()
        self.assertEqual(self.lifecycle[:2], ["listener", "snapshot"])
        self.assertEqual(set(self.subscriptions), {"espresense/devices/example-collar/example-a",
                                                 "espresense/devices/example-collar/example-b", "frigate/events"})
        await self.observation(0, retained=True)
        self.assertEqual(self.hass.states.get("binary_sensor.example_pet_recently_seen").state, "off")
        for offset in (0, 15, 30):
            await self.observation(offset)
        self.assertEqual(self.hass.states.get("sensor.example_pet_room").state, "room_a")
        self.assertEqual(self.hass.states.get("sensor.example_pet_light_entry").state, "blue")
        self.assertEqual(self.hass.states.get("binary_sensor.example_pet_near_entry").state, "on")
        self.assertEqual(self.hass.states.get("sensor.example_pet_health").attributes["storage_ok"], True)

    async def test_initially_disconnected_reconnect_duplicates_and_shutdown(self):
        self.initial_connected = False
        await self.start()
        self.assertEqual(self.hass.states.get("sensor.example_pet_health").state, "transport_unavailable")
        self.status_callbacks[0](True)
        await self.flush()
        since = self.coordinator.engine.monitored_since
        self.clock.now += 10
        self.status_callbacks[0](True)
        await self.flush()
        self.assertEqual(self.coordinator.engine.monitored_since, since)
        await self.coordinator.async_stop()
        self.assertEqual(set(self.removed), {"status", *self.subscriptions})
        self.assertTrue(self.coordinator.worker.done())
        self.assertFalse(self.hass.services.has_service(DOMAIN, "acknowledge"))

    async def test_actual_contact_transition_persistence_ack_and_camera_reference(self):
        await self.start()
        await self.observation(0)
        self.hass.states.async_set("binary_sensor.example_entry", "on")
        await self.flush()
        self.assertEqual(self.events, [])
        await self.open_door(1)
        self.assertEqual(self.events[-1]["level"], "heads_up")
        await self.camera(2)
        self.assertEqual(self.hass.states.get("sensor.example_pet_alert").state, "suspected")
        self.assertEqual(self.events[-1]["reason"], "camera_inside")
        self.assertEqual(self.events[-1]["camera_reference"], {"camera": "example-camera", "event_id": "synthetic-event"})
        saved = await self.coordinator.store.async_load()
        self.assertEqual(saved["engine"]["alert"]["level"], "suspected")
        self.assertEqual(saved["camera_sources"]["entry"]["event_id"], "synthetic-event")
        await self.hass.services.async_call(DOMAIN, "acknowledge", {}, blocking=True)
        await self.flush()
        alert = self.hass.states.get("sensor.example_pet_alert")
        self.assertTrue(alert.attributes["acknowledged"])
        self.assertEqual(alert.state, "suspected")
        self.assertNotIn("synthetic-event", str(alert.attributes))
        saved = await self.coordinator.store.async_load()
        self.assertTrue(saved["engine"]["alert"]["acknowledged"])

    async def test_failed_recovery_save_keeps_latch_and_exposes_durability(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        await self.camera(2)
        with patch.object(self.coordinator.store, "async_save", new=AsyncMock(side_effect=OSError("private-marker"))):
            for offset in (3, 18, 33, 48, 63):
                await self.observation(offset)
            self.assertEqual(self.hass.states.get("sensor.example_pet_alert").state, "suspected")
            self.assertFalse(self.hass.states.get("sensor.example_pet_health").attributes["storage_ok"])
            self.assertNotIn("recovered", [event["level"] for event in self.events])
        for offset in (64, 79, 94, 109, 124):
            await self.observation(offset)
        self.assertEqual(self.hass.states.get("sensor.example_pet_alert").state, "clear")
        self.assertEqual(self.events[-1]["level"], "recovered")
        self.assertNotIn("private-marker", str(self.hass.states.async_all()))

    async def test_failed_outputs_coalesce_to_current_severity_before_delivery(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        self.events.clear()
        with patch.object(self.coordinator.store, "async_save", new=AsyncMock(side_effect=OSError("private-marker"))):
            await self.camera(2)
            await self.camera(3, "walkway", "second-event")
        self.assertEqual(self.events, [])
        self.coordinator.enqueue("advance", (), self.clock.monotonic())
        await self.flush()
        self.assertEqual([event["level"] for event in self.events], ["urgent"])
        for offset in (4, 19, 34, 49, 64):
            await self.observation(offset)
        self.assertEqual([event["level"] for event in self.events], ["urgent", "recovered"])

    async def test_overflow_discards_queued_positive_evidence_and_preserves_latch(self):
        await self.start()
        for offset in (0, 15, 30):
            await self.observation(offset)
        await self.open_door(31)
        await self.camera(32)
        self.clock.now = 1033
        for _ in range(QUEUE_LIMIT + 1):
            self.coordinator.enqueue("observe", ("node_a", 1, -60), self.clock.monotonic())
        self.assertLessEqual(self.coordinator.queue.qsize(), QUEUE_LIMIT)
        await self.flush()
        self.assertTrue(self.hass.states.get("sensor.example_pet_health").attributes["overflow"])
        self.assertEqual(self.hass.states.get("sensor.example_pet_room").state, "unknown")
        self.assertEqual(self.hass.states.get("binary_sensor.example_pet_near_entry").state, "unknown")
        self.assertEqual(self.hass.states.get("sensor.example_pet_alert").state, "suspected")
        self.assertEqual(self.hass.states.get("sensor.example_pet_light_entry").state, "red")
        await self.observation(34)
        self.assertEqual(self.hass.states.get("sensor.example_pet_room").state, "unknown")

    async def test_restart_restores_latch_reference_and_ack_but_no_positive_evidence(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        await self.camera(2)
        await self.hass.services.async_call(DOMAIN, "acknowledge", {}, blocking=True)
        await self.coordinator.async_stop()
        restarted = Coordinator(self.hass, self.config, clock=self.clock.monotonic, wall=self.clock.wall)
        self.hass.data[DOMAIN] = self.coordinator = restarted
        self.assertTrue(await restarted.async_start())
        await self.flush()
        snapshot = restarted.state
        self.assertEqual(snapshot["alert"]["level"], "suspected")
        self.assertTrue(snapshot["alert"]["acknowledged"])
        self.assertFalse(snapshot["recently_seen"])
        self.assertIsNone(snapshot["doors"]["entry"]["near"])
        self.clock.now = 1182
        restarted.enqueue("advance", (), self.clock.monotonic())
        await self.flush()
        self.assertEqual(self.events[-1]["level"], "urgent")
        self.assertEqual(self.events[-1]["camera_reference"]["event_id"], "synthetic-event")

    async def test_invalid_private_store_stops_setup_instead_of_clearing_state(self):
        coordinator = Coordinator(self.hass, self.config)
        await coordinator.store.async_save({"schema": 1, "engine": {}, "camera_sources": {}})
        with self.assertLogs("custom_components.espresense_pet.coordinator", level="ERROR") as logs:
            self.assertFalse(await coordinator.async_start())
        self.assertIsNone(coordinator.worker)
        self.assertEqual(self.subscriptions, {})
        self.assertNotIn("Traceback", "\n".join(logs.output))

    async def test_corrupt_disk_store_and_subsequent_quarantine_restart_both_fail_closed(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        await self.camera(2)
        path = Path(self.coordinator.store.path)
        await self.coordinator.async_stop()
        await self.hass.async_add_executor_job(path.write_text, "{private-marker", "utf-8")
        for attempt in range(2):
            self.coordinator = Coordinator(self.hass, self.config, clock=self.clock.monotonic, wall=self.clock.wall)
            self.hass.data[DOMAIN] = self.coordinator
            self.coordinator.store._manager.async_invalidate(self.coordinator.store.key)
            with self.assertLogs(level="ERROR") as logs:
                self.assertFalse(await self.coordinator.async_start(), f"Corrupt-state restart {attempt} accepted a clear state")
            self.assertNotIn("private-marker", "\n".join(logs.output))
            self.assertIsNone(self.coordinator.worker)
        self.assertFalse(await self.hass.async_add_executor_job(path.exists))
        quarantined = await self.hass.async_add_executor_job(lambda: list(path.parent.glob(path.name + ".corrupt.*")))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(await self.hass.async_add_executor_job(quarantined[0].read_text, "utf-8"), "{private-marker")

    async def test_mqtt_unavailable_and_partial_subscription_failure_clean_up(self):
        coordinator = Coordinator(self.hass, self.config)
        with patch("homeassistant.components.mqtt.async_wait_for_mqtt_client", new=AsyncMock(return_value=False)):
            self.assertFalse(await coordinator.async_start())
        self.assertTrue(coordinator.worker.done())
        self.assertEqual(self.subscriptions, {})
        coordinator = Coordinator(self.hass, self.config)
        removed = []
        subscribe = AsyncMock(side_effect=[lambda: removed.append("first"), OSError("private-marker")])
        with patch("homeassistant.components.mqtt.async_subscribe", new=subscribe):
            with self.assertLogs("custom_components.espresense_pet.coordinator", level="ERROR") as logs:
                self.assertFalse(await coordinator.async_start())
        self.assertEqual(removed, ["first"])
        self.assertIn("status", self.removed)
        self.assertTrue(coordinator.worker.done())
        self.assertNotIn("private-marker", "\n".join(logs.output))

    async def test_health_intent_does_not_arrive_after_reception_recovers(self):
        await self.start()
        self.events.clear()
        self.clock.now = 2800
        with patch.object(self.coordinator.store, "async_save", new=AsyncMock(side_effect=OSError("private-marker"))):
            # Force a persistence retry to exercise withheld health delivery.
            self.coordinator.storage_ok = False
            self.coordinator.enqueue("advance", (), self.clock.monotonic())
            await self.flush()
        self.assertEqual(self.events, [])
        await self.observation(1801)
        self.assertEqual(self.hass.states.get("sensor.example_pet_health").state, "ok")
        self.assertEqual(self.events, [])

    async def test_incident_event_waits_for_actual_store_write(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        self.events.clear()
        started, release = asyncio.Event(), asyncio.Event()
        save = self.coordinator.store.async_save

        async def delayed_save(data):
            started.set()
            await release.wait()
            await save(data)

        with patch.object(self.coordinator.store, "async_save", new=delayed_save):
            delivery = asyncio.create_task(self.camera(2))
            try:
                await asyncio.wait_for(started.wait(), 3)
                self.assertEqual(self.events, [])
                stored = await self.coordinator.store.async_load()
                self.assertEqual(stored["engine"]["alert"]["level"], "clear")
            finally:
                release.set()
                await asyncio.wait_for(delivery, 3)
        self.assertEqual(self.events[-1]["level"], "suspected")
        self.assertEqual((await self.coordinator.store.async_load())["engine"]["alert"]["level"], "suspected")

    async def test_real_one_second_timer_advances_health_without_manual_tick(self):
        self.config["timing"]["health_silence_s"] = 1
        await self.start()
        observed = asyncio.Event()

        @callback
        def health_changed(event):
            state = event.data.get("new_state")
            if event.data["entity_id"] == "sensor.example_pet_health" and state is not None and state.state == "device_silence":
                observed.set()

        unsubscribe = self.hass.bus.async_listen("state_changed", health_changed)
        try:
            self.clock.now = 1001
            await self.hass.async_start()
            await asyncio.wait_for(observed.wait(), 4)
            await self.flush()
            self.assertEqual(self.events[-1]["level"], "health")
        finally:
            unsubscribe()

    async def test_health_publication_precedes_light_intent_during_store_failure(self):
        await self.start()
        order = []
        remove_light = self.coordinator.listen(lambda: order.append("light"), priority=1)
        remove_health = self.coordinator.listen(lambda: order.append("health"), priority=0)
        await self.observation(0)
        self.assertEqual(order[-2:], ["health", "light"])
        remove_light()
        remove_health()
        await self.open_door(1)
        state_events = []

        @callback
        def changed(event):
            state_events.append(event.data["entity_id"])

        unsubscribe = self.hass.bus.async_listen("state_changed", changed)
        try:
            with patch.object(self.coordinator.store, "async_save", new=AsyncMock(side_effect=OSError("private-marker"))):
                await self.camera(2)
            self.assertLess(state_events.index("sensor.example_pet_health"), state_events.index("sensor.example_pet_light_entry"))
            self.assertFalse(self.hass.states.get("sensor.example_pet_health").attributes["storage_ok"])
            self.assertEqual(self.hass.states.get("sensor.example_pet_light_entry").state, "red")
        finally:
            unsubscribe()

    async def test_slow_storage_cannot_turn_queued_old_observations_into_recovery(self):
        await self.start()
        await self.observation(0)
        await self.open_door(1)
        await self.camera(2)
        started, release = asyncio.Event(), asyncio.Event()
        save = self.coordinator.store.async_save

        async def delayed_save(data):
            started.set()
            await release.wait()
            await save(data)

        with patch.object(self.coordinator.store, "async_save", new=delayed_save):
            self.clock.now = 1003
            self.coordinator.enqueue("acknowledge", (), self.clock.monotonic())
            await asyncio.wait_for(started.wait(), 3)
            try:
                for offset in (4, 19, 34, 49, 64):
                    self.clock.now = 1000 + offset
                    self.coordinator.enqueue("observe", ("node_a", 1, -60), self.clock.monotonic())
                self.clock.now = 1100
            finally:
                release.set()
            await self.flush()
        self.assertEqual(self.coordinator.state["alert"]["level"], "suspected")
        self.assertIsNone(self.coordinator.state["room"])
        self.assertIsNone(self.coordinator.state["doors"]["entry"]["near"])
        self.assertNotIn("recovered", [event["level"] for event in self.events])

    async def test_old_queued_camera_frame_cannot_create_a_new_latch(self):
        await self.start()
        await self.open_door(1)
        self.clock.now = 1100
        self.coordinator.enqueue("camera", ("entry", "outside", "queued-camera", 1002), 1002)
        await self.flush()
        self.assertEqual(self.coordinator.state["alert"]["level"], "clear")
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
