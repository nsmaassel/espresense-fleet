"""Injected-time domain behavior; no MQTT, Home Assistant or household devices."""
import copy
import unittest

from custom_components.espresense_pet.engine import Engine
from test_pet_config import example_config


def engine():
    result = Engine(example_config())
    result.transport(True, 0)
    return result


def incident(result, level="inside"):
    result.observe("node_a", 1, -60, 0)
    result.door_open("entry", 1)
    return result.camera("entry", level, "example-event", 2, 2)


class PetEngineTests(unittest.TestCase):
    def test_room_requires_continuing_receipts_not_a_tick(self):
        result = engine()
        result.observe("node_a", 1, -60, 0)
        result.advance(30)
        self.assertIsNone(result.snapshot(30)["room"])
        result.observe("node_a", 1, -60, 31)
        result.observe("node_a", 1, -60, 46)
        result.observe("node_a", 1, -60, 61)
        self.assertEqual(result.snapshot(61)["room"], "room_a")
        self.assertEqual(result.snapshot(61)["last_seen_age_s"], 0)

    def test_identical_reports_refresh_and_exact_freshness_gap_is_allowed(self):
        result = engine()
        for now in (0, 20, 40):
            result.observe("node_a", 1, -60, now)
        self.assertEqual(result.snapshot(40)["room"], "room_a")
        self.assertTrue(result.snapshot(60)["doors"]["entry"]["near"])
        self.assertIsNone(result.snapshot(60.01)["doors"]["entry"]["near"])

    def test_previously_accepted_room_needs_a_new_hold_after_receipt_gap(self):
        result = engine()
        for now in (0, 15, 30):
            result.observe("node_a", 1, -60, now)
        result.advance(51)
        self.assertIsNone(result.snapshot(51)["room"])
        for now in (52, 67):
            result.observe("node_a", 1, -60, now)
            self.assertIsNone(result.snapshot(now)["room"])
            self.assertEqual(result.snapshot(now)["last_room"], "room_a")
        result.observe("node_a", 1, -60, 82)
        self.assertEqual(result.snapshot(82)["room"], "room_a")

    def test_previously_accepted_room_needs_a_new_hold_after_reconnection(self):
        result = engine()
        for now in (0, 15, 30):
            result.observe("node_a", 1, -60, now)
        result.transport(False, 31)
        result.transport(True, 32)
        for now in (33, 48):
            result.observe("node_a", 1, -60, now)
            self.assertIsNone(result.snapshot(now)["room"])
            self.assertEqual(result.snapshot(now)["last_room"], "room_a")
        result.observe("node_a", 1, -60, 63)
        self.assertEqual(result.snapshot(63)["room"], "room_a")

    def test_return_to_previously_accepted_room_after_contradiction_needs_hold(self):
        result = engine()
        for now in (0, 15, 30):
            result.observe("node_a", 1, -60, now)
        result.observe("node_b", 0.5, -60, 31)
        self.assertIsNone(result.snapshot(31)["room"])
        for now in (32, 47):
            result.observe("node_a", 0.1, -60, now)
            self.assertIsNone(result.snapshot(now)["room"])
        result.observe("node_a", 0.1, -60, 62)
        self.assertEqual(result.snapshot(62)["room"], "room_a")

    def test_unqualified_return_refreshes_seen_history_but_not_room_history(self):
        for interruption in ("gap", "disconnect", "contradiction"):
            with self.subTest(interruption=interruption):
                result = engine()
                for now in (0, 15, 30):
                    result.observe("node_a", 1, -60, now)
                if interruption == "gap":
                    result.advance(51)
                elif interruption == "disconnect":
                    result.transport(False, 31)
                    result.transport(True, 32)
                else:
                    result.observe("node_b", 0.5, -60, 31)
                result.observe("node_a", 0.1, -60, 52)
                self.assertIsNone(result.snapshot(52)["room"])
                self.assertEqual(result.snapshot(630)["last_room"], "room_a")
                self.assertIsNone(result.snapshot(631)["last_room"])
                self.assertTrue(result.snapshot(952)["recently_seen"])
                self.assertFalse(result.snapshot(953)["recently_seen"])

    def test_same_room_ties_are_valid_cross_room_ties_are_unknown(self):
        config = example_config()
        config["nodes"]["node_c"] = {"mqtt_room": "example-c", "room": "room_a"}
        result = Engine(config)
        result.transport(True, 0)
        for now in (0, 15, 30):
            result.observe("node_a", 1, -60, now)
            result.observe("node_c", 1, -60, now)
        self.assertEqual(result.snapshot(30)["room"], "room_a")
        result.observe("node_b", 1, -60, 31)
        self.assertIsNone(result.snapshot(31)["room"])
        self.assertEqual(result.snapshot(31)["last_room"], "room_a")

    def test_farther_node_receipts_do_not_extend_the_winners_hold(self):
        result = engine()
        result.observe("node_a", 1, -60, 0)
        result.observe("node_b", 5, -90, 15)
        result.observe("node_b", 5, -90, 30)
        self.assertIsNone(result.snapshot(30)["room"])

    def test_history_and_recent_evidence_expire_independently(self):
        result = engine()
        for now in (0, 15, 30):
            result.observe("node_a", 1, -60, now)
        self.assertEqual(result.snapshot(630)["last_room"], "room_a")
        self.assertIsNone(result.snapshot(631)["last_room"])
        self.assertTrue(result.snapshot(930)["recently_seen"])
        self.assertFalse(result.snapshot(931)["recently_seen"])

    def test_door_proximity_requires_local_rssi_and_light_is_not_safety(self):
        result = engine()
        self.assertEqual(result.snapshot(0)["doors"]["entry"], {"near": None, "light": "unknown"})
        result.observe("node_b", 5, -90, 0)
        self.assertIsNone(result.snapshot(0)["doors"]["entry"]["near"])
        result.observe("node_a", 2, None, 1)
        self.assertIsNone(result.snapshot(1)["doors"]["entry"]["near"])
        result.observe("node_a", 2, -66, 2)
        self.assertEqual(result.snapshot(2)["doors"]["entry"], {"near": False, "light": "off"})
        result.observe("node_a", 2, -65, 3)
        self.assertEqual(result.snapshot(3)["doors"]["entry"], {"near": True, "light": "blue"})

    def test_exterior_heads_up_has_exact_cooldown_internal_door_does_not(self):
        config = example_config()
        config["doors"]["back"]["exterior"] = False
        result = Engine(config)
        result.transport(True, 0)
        result.observe("node_a", 1, -60, 0)
        self.assertEqual(result.door_open("entry", 1)[0]["level"], "heads_up")
        result.observe("node_a", 1, -60, 60)
        self.assertEqual(result.door_open("entry", 60), [])
        self.assertEqual(result.door_open("entry", 61)[0]["level"], "heads_up")
        result.observe("node_b", 1, -60, 62)
        self.assertEqual(result.door_open("back", 62), [])
        self.assertEqual(result.camera("back", "outside", "internal-event", 63, 63), [])

    def test_inside_latches_suspected_outside_can_start_urgent(self):
        result = engine()
        self.assertEqual(incident(result)[0]["level"], "suspected")
        result.acknowledge(3)
        self.assertTrue(result.snapshot(3)["alert"]["acknowledged"])
        upgraded = result.camera("entry", "outside", "example-event", 4, 4)
        self.assertEqual(upgraded[0]["level"], "urgent")
        self.assertFalse(result.snapshot(4)["alert"]["acknowledged"])
        other = engine()
        self.assertEqual(incident(other, "outside")[0]["level"], "urgent")

    def test_camera_correlation_uses_same_door_and_observation_time(self):
        result = engine()
        result.door_open("entry", 10)
        self.assertEqual(result.camera("back", "outside", "wrong-door", 11, 11), [])
        self.assertEqual(result.camera("entry", "inside", "before-open", 9, 12), [])
        self.assertEqual(result.camera("entry", "inside", "future", 14, 13), [])
        self.assertEqual(result.camera("entry", "inside", "too-late", 191, 191), [])
        self.assertEqual(result.snapshot(191)["alert"]["level"], "clear")

    def test_camera_exact_correlation_boundary_is_accepted(self):
        result = engine()
        result.door_open("entry", 10)
        self.assertEqual(result.camera("entry", "inside", "boundary", 190, 190)[0]["level"], "suspected")

    def test_stale_delivery_is_rejected_even_if_old_frame_correlated(self):
        result = engine()
        result.door_open("entry", 0)
        self.assertEqual(result.camera("entry", "inside", "old-frame", 1, 182), [])

    def test_independent_second_door_upgrade_keeps_both_origins_red(self):
        result = engine()
        incident(result)
        result.acknowledge(3)
        result.door_open("back", 4)
        self.assertEqual(result.camera("back", "outside", "second-door", 5, 5)[0]["level"], "urgent")
        state = result.snapshot(5)
        self.assertEqual(state["alert"]["door"], "back")
        self.assertEqual(state["alert"]["doors"], ["back", "entry"])
        self.assertFalse(state["alert"]["acknowledged"])
        self.assertEqual([door["light"] for door in state["doors"].values()], ["red", "red"])

    def test_silence_without_incident_never_creates_escape(self):
        result = engine()
        result.observe("node_a", 1, -60, 0)
        result.advance(1000)
        self.assertEqual(result.snapshot(1000)["alert"]["level"], "clear")

    def test_monitored_silence_urgent_boundary(self):
        result = engine()
        incident(result)
        self.assertEqual(result.advance(181), [])
        intents = result.advance(182)
        self.assertEqual(intents[0]["level"], "urgent")
        self.assertEqual(result.advance(183), [])

    def test_transport_outage_interrupts_silence_and_hides_positive_radio_state(self):
        result = engine()
        incident(result)
        result.transport(False, 10)
        self.assertEqual(result.snapshot(10)["health"], "transport_unavailable")
        self.assertIsNone(result.snapshot(10)["doors"]["entry"]["near"])
        self.assertEqual(result.snapshot(10)["doors"]["entry"]["light"], "red")
        self.assertEqual(result.advance(1000), [])
        self.assertEqual(result.snapshot(1000)["alert"]["level"], "suspected")
        result.transport(True, 1000)
        self.assertEqual(result.advance(1179), [])
        self.assertEqual(result.advance(1180)[0]["level"], "urgent")

    def test_recovery_needs_receipts_after_incident_and_ack_never_clears(self):
        result = engine()
        incident(result)
        result.acknowledge(3)
        result.observe("node_a", 1, -60, 4)
        result.advance(64)
        self.assertEqual(result.snapshot(64)["alert"]["level"], "suspected")
        for now in (65, 80, 95, 110):
            self.assertEqual(result.observe("node_a", 1, -60, now), [])
        recovered = result.observe("node_a", 1, -60, 125)
        self.assertEqual(recovered[0]["level"], "recovered")
        self.assertEqual(result.snapshot(125)["alert"]["level"], "clear")
        self.assertFalse(result.snapshot(125)["alert"]["acknowledged"])

    def test_recovery_gap_and_room_contradiction_reset_timer(self):
        result = engine()
        incident(result)
        for now in (3, 23, 44):
            result.observe("node_a", 1, -60, now)
        result.observe("node_b", 0.5, -60, 45)
        for now in (46, 66, 86):
            self.assertEqual(result.observe("node_a", 0.1, -60, now), [])
        self.assertEqual(result.observe("node_a", 0.1, -60, 106)[0]["level"], "recovered")

    def test_transport_loss_resets_recovery(self):
        result = engine()
        incident(result)
        for now in (3, 18, 33, 48):
            result.observe("node_a", 1, -60, now)
        result.transport(False, 49)
        result.transport(True, 50)
        for now in (51, 66, 81, 96):
            self.assertEqual(result.observe("node_a", 1, -60, now), [])
        self.assertEqual(result.observe("node_a", 1, -60, 111)[0]["level"], "recovered")

    def test_dedup_and_recovery_cutoff_prevent_old_evidence_reopening(self):
        result = engine()
        incident(result)
        self.assertEqual(result.camera("entry", "inside", "example-event", 3, 3), [])
        for now in (4, 19, 34, 49, 64):
            result.observe("node_a", 1, -60, now)
        self.assertEqual(result.snapshot(64)["alert"]["level"], "clear")
        result.door_open("entry", 65)
        self.assertEqual(result.camera("entry", "inside", "example-event", 66, 66), [])
        self.assertEqual(result.camera("entry", "outside", "old-stage", 64, 67), [])
        self.assertEqual(result.camera("entry", "inside", "new-event", 68, 68)[0]["level"], "suspected")

    def test_restart_preserves_severity_origins_ack_and_dedup_not_freshness(self):
        original = engine()
        incident(original)
        original.acknowledge(3)
        state = original.dump()
        restarted = Engine(example_config(), restored=state)
        snapshot = restarted.snapshot(0)
        self.assertEqual(snapshot["alert"], original.snapshot(3)["alert"])
        self.assertFalse(snapshot["recently_seen"])
        self.assertIsNone(snapshot["last_seen_age_s"])
        self.assertIsNone(snapshot["room"])
        self.assertIsNone(snapshot["doors"]["entry"]["near"])
        restarted.transport(True, 10)
        self.assertEqual(restarted.advance(189), [])
        self.assertEqual(restarted.advance(190)[0]["level"], "urgent")

    def test_recovered_event_tombstones_survive_restart_without_raw_ids(self):
        original = engine()
        incident(original)
        for now in (3, 18, 33, 48, 63):
            original.observe("node_a", 1, -60, now)
        self.assertEqual(original.snapshot(63)["alert"]["level"], "clear")
        persisted = original.dump()
        self.assertNotIn("example-event", str(persisted))
        restarted = Engine(example_config(), restored=persisted)
        restarted.transport(True, 0)
        restarted.door_open("entry", 1)
        self.assertEqual(restarted.camera("entry", "inside", "example-event", 2, 2), [])
        self.assertEqual(restarted.snapshot(2)["alert"]["level"], "clear")

    def test_lower_severity_second_door_keeps_global_severity_and_origin(self):
        result = engine()
        incident(result, "outside")
        result.door_open("back", 3)
        self.assertEqual(result.camera("back", "inside", "second-origin", 4, 4), [])
        snapshot = result.snapshot(4)
        self.assertEqual(snapshot["alert"]["level"], "urgent")
        self.assertEqual(snapshot["alert"]["door"], "entry")
        self.assertEqual(snapshot["alert"]["doors"], ["back", "entry"])

    def test_health_outage_restarts_full_monitoring_interval(self):
        result = engine()
        result.transport(False, 1799)
        self.assertEqual(result.advance(10_000), [])
        result.transport(True, 10_000)
        self.assertEqual(result.advance(11_799), [])
        self.assertEqual(result.advance(11_800)[0]["level"], "health")

    def test_invalid_restore_fails_instead_of_silently_clearing_latch(self):
        source = engine()
        incident(source)
        original = source.dump()
        for mutate in [lambda s: s.update(schema=True), lambda s: s.update(pet_id="different_pet"),
                       lambda s: s["alert"].update(level="invented"),
                       lambda s: s["alert"].update(door="unknown"),
                       lambda s: s["alert"].update(acknowledged="yes"),
                       lambda s: s.update(extra="private-marker")]:
            data = copy.deepcopy(original)
            mutate(data)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                Engine(example_config(), restored=data)

    def test_health_advisory_once_per_continuously_monitored_episode(self):
        result = engine()
        self.assertEqual(result.snapshot(1799)["health"], "never_seen")
        self.assertEqual(result.advance(1800)[0]["level"], "health")
        self.assertEqual(result.snapshot(1800)["health"], "device_silence")
        self.assertEqual(result.advance(3600), [])
        result.observe("node_a", 1, -60, 3601)
        self.assertEqual(result.snapshot(3601)["health"], "ok")
        self.assertEqual(result.advance(5401)[0]["level"], "health")

    def test_invalid_calls_do_not_mutate_or_advance_the_clock(self):
        calls = [lambda e: e.observe("unknown", 1, -60, 100),
                 lambda e: e.observe("node_a", True, -60, 100),
                 lambda e: e.observe("node_a", 1, float("nan"), 100),
                 lambda e: e.observe("node_a", 10 ** 400, -60, 100),
                 lambda e: e.door_open("unknown", 100),
                 lambda e: e.camera("entry", "invented", "event", 100, 100),
                 lambda e: e.transport(1, 100), lambda e: e.advance(float("inf")),
                 lambda e: e.advance(-1)]
        for call in calls:
            result = engine()
            original = result.dump()
            with self.subTest(call=call), self.assertRaises(ValueError):
                call(result)
            self.assertEqual(result.dump(), original)
            result.advance(1)
        with self.assertRaises(ValueError):
            result.advance(0)

    def test_disconnected_observations_cannot_restore_positive_freshness(self):
        result = Engine(example_config())
        self.assertEqual(result.observe("node_a", 1, -60, 1), [])
        self.assertFalse(result.snapshot(1)["recently_seen"])

    def test_camera_dedup_storage_is_bounded_and_snapshots_are_detached(self):
        result = engine()
        result.door_open("entry", 0)
        for index in range(300):
            result.camera("entry", "inside", f"event-{index}", 1, 1)
        stored = result.dump()
        self.assertLessEqual(len(stored["camera_seen"]), 256)
        stored["alert"]["level"] = "clear"
        self.assertEqual(result.snapshot(1)["alert"]["level"], "suspected")


if __name__ == "__main__":
    unittest.main()
