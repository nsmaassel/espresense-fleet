import json
import unittest

from custom_components.espresense_pet.ingress import camera_events, device_observation


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "timing": {"observation_fresh_s": 20},
            "doors": {"entry": {"camera": "example_camera", "inside_zones": ["threshold"],
                                  "outside_zones": ["walkway"], "exterior": True},
                      "inside": {"camera": "example_camera", "inside_zones": ["threshold"],
                                   "outside_zones": [], "exterior": False}},
        }
        self.event = {"type": "update", "before": {"current_zones": []}, "after": {
            "id": "synthetic-event", "camera": "example_camera", "label": "cat",
            "false_positive": False, "frame_time": 1999999995, "end_time": None,
            "current_zones": ["threshold"], "entered_zones": ["walkway"],
        }}

    def camera(self, value=None, retained=False):
        return camera_events(json.dumps(value or self.event), retained, self.config,
                             wall_now=2000000000, monotonic_now=100)

    def test_device_keeps_only_measurements_and_rejects_retained(self):
        payload = json.dumps({"distance": 1.5, "rssi": -65, "ip": "drop-marker", "name": "drop-marker"})
        self.assertEqual(device_observation(payload, False), (1.5, -65))
        self.assertIsNone(device_observation(payload, True))
        self.assertEqual(device_observation('{"distance":2}', False), (2, None))

    def test_bad_device_data_is_ignored_without_echo(self):
        for payload in ('{}', '[]', '{"distance":true}', '{"distance":-1}',
                        '{"distance":NaN}', '{"distance":1,"distance":2}',
                        '{"distance":1,"rssi":false}', '{"distance":1,"rssi":2}',
                        '{"distance":' + str(10**400) + '}', '[' * 1100, 'x' * 17000):
            with self.subTest(payload_length=len(payload)):
                self.assertIsNone(device_observation(payload, False))

    def test_camera_uses_current_new_zone_and_converts_frame_time(self):
        self.assertEqual(self.camera(), [{"door": "entry", "zone": "inside",
                                         "event_id": "synthetic-event", "evidence_at": 95}])
        self.event["before"]["current_zones"] = ["threshold"]
        self.assertEqual(self.camera(), [])
        self.event["after"]["current_zones"] = ["walkway"]
        self.assertEqual(self.camera()[0]["zone"], "outside")

    def test_camera_outside_wins_when_both_zones_new(self):
        self.event["after"]["current_zones"] = ["threshold", "walkway"]
        self.assertEqual([row["zone"] for row in self.camera()], ["outside"])

    def test_stale_future_false_positive_ended_and_wrong_camera_do_not_count(self):
        for key, value in (("frame_time", 1999999979), ("frame_time", 2000000001),
                           ("frame_time", True), ("frame_time", float("nan")),
                           ("false_positive", True), ("false_positive", "false"),
                           ("end_time", 1999999999), ("label", "person"),
                           ("camera", "unmapped"), ("current_zones", "threshold"),
                           ("id", "invalid event id"), ("id", "x" * 129)):
            event = json.loads(json.dumps(self.event))
            event["after"][key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(self.camera(event), [])
        self.assertEqual(self.camera(retained=True), [])
        self.event["type"] = "end"
        self.assertEqual(self.camera(), [])

    def test_malformed_nested_and_duplicate_camera_payloads_are_ignored(self):
        for payload in ('[]', '{}', '[' * 1100, 'x' * 17000,
                        '{"type":"new","type":"update"}'):
            self.assertEqual(camera_events(payload, False, self.config, wall_now=2000000000,
                                           monotonic_now=100), [])


if __name__ == "__main__":
    unittest.main()
