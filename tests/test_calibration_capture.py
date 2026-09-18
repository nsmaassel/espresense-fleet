"""Transport is injected; no live broker, credentials, or hardware are involved."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tooling.calibration.capture import capture, normalize, validate_config
from tooling.calibration.process import bounded_process, capture_file
from tooling.calibration.records import load_log
from test_calibration import log_text, schedule


def config():
    return {"schema": 1, "device_alias": "example-phone", "node_map": {"fictional-a": "node01", "fictional-b": "node02", "fictional-c": "node03"}}


class Clock:
    now = 0
    def __call__(self):
        return self.now


class Client:
    def __init__(self, clock, behavior="success"):
        self.clock, self.behavior, self.step = clock, behavior, 0
        self.on_connect = self.on_subscribe = self.on_message = self.on_disconnect = None

    def connect(self, host, port, keepalive):
        if self.behavior == "connect_error":
            raise OSError("sensitive transport detail")
        return 0

    def subscribe(self, topics):
        self.topics = topics
        return (0, 7)

    def loop(self, timeout):
        self.clock.now += timeout
        self.step += 1
        if self.behavior == "timeout":
            return 0
        if self.step == 1:
            self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)
        elif self.step == 2:
            code = SimpleNamespace(is_failure=self.behavior == "denied")
            self.on_subscribe(self, None, 7, [code] * len(self.topics), None)
        elif self.behavior == "disconnect":
            self.on_disconnect(self, None, None, None, None)
        elif self.behavior == "loop_error":
            return 7
        else:
            self.on_message(self, None, SimpleNamespace(topic="espresense/devices/example-phone/fictional-a", retain=False,
                            payload=b'{"distance":2,"rssi":-60,"name":"sensitive transport detail","int":123}'))
        return 0

    def disconnect(self):
        return 0


def stalled_child(path):
    Path(path).write_text("partial", encoding="utf-8")
    time.sleep(30)


class CaptureTests(unittest.TestCase):
    def test_normalize_drops_raw_fields_and_requires_exact_allowlisted_topics(self):
        cfg = validate_config(config(), schedule())
        payload = b'{"distance":4,"rssi":-65,"mac":"never-persist","name":"never-persist","int":999}'
        row, reason = normalize("espresense/devices/example-phone/fictional-a", payload, False, 27, cfg)
        self.assertEqual(row, {"schema": 1, "kind": "device", "elapsed_ms": 27, "node": "node01", "distance_m": 4, "rssi_dbm": -65})
        self.assertIsNone(reason)
        for topic in ["espresense/devices/example-phone/fictional-a/rssi", "espresense/devices/other/fictional-a",
                      "espresense/rooms/fictional-a/status", "espresense/devices/example-phone/unknown"]:
            self.assertEqual(normalize(topic, payload, False, 27, cfg), (None, "ignored"))
        self.assertEqual(normalize("espresense/devices/example-phone/fictional-a", payload, True, 27, cfg), (None, "retained"))
        self.assertEqual(normalize("espresense/devices/example-phone/fictional-a", b'{"distance":true}', False, 27, cfg), (None, "invalid"))
        peer, _ = normalize("espresense/devices/node:fictional-b/fictional-a", payload, False, 27, cfg)
        self.assertEqual((peer["node"], peer["peer"]), ("node01", "node02"))
        wifi, _ = normalize("espresense/rooms/fictional-a/telemetry", b'{"rssi":-75,"ip":"never-persist"}', False, 28, cfg)
        self.assertEqual(wifi["kind"], "wifi")

    def test_rejects_raw_selector_and_invalid_node_maps(self):
        for selector in ["irk:do-not-accept", "aabbccddeeff", "aa-bb-cc-dd-ee-ff", "node:abc", "#", "a/b"]:
            cfg = config()
            cfg["device_alias"] = selector
            with self.assertRaises(ValueError):
                validate_config(cfg, schedule())
        cfg = config()
        cfg["node_map"]["fictional-b"] = "node01"
        with self.assertRaises(ValueError):
            validate_config(cfg, schedule())

    def run_capture(self, behavior):
        clock, stream = Clock(), io.StringIO()
        result = capture(stream, config(), schedule(), 8000, Client(clock, behavior), clock,
                         host="synthetic.invalid", connect_timeout=1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(stream.getvalue(), encoding="utf-8")
            parsed = load_log(path)
        self.assertNotIn("sensitive", stream.getvalue())
        return result, parsed, clock.now

    def test_capture_monotonic_time_and_exact_duration_bound(self):
        end, log, elapsed = self.run_capture("success")
        self.assertTrue(end["complete"])
        self.assertTrue(all(0 <= r["elapsed_ms"] < 8000 for r in log["records"]))
        self.assertEqual(log["records"][0]["elapsed_ms"], 250)
        self.assertLessEqual(elapsed, 9)

    def test_arbitrary_millisecond_durations_replay_as_complete(self):
        for duration in (1001, 1003, 1011, 8001):
            with self.subTest(duration=duration):
                clock, stream = Clock(), io.StringIO()
                plan = schedule()
                plan["stops"] = [{"room": "room01", "start_ms": 0, "end_ms": duration}]
                end = capture(stream, config(), plan, duration, Client(clock), clock,
                              host="synthetic.invalid", connect_timeout=1)
                self.assertEqual(end["elapsed_ms"], duration)
                self.assertTrue(end["complete"])
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "capture.jsonl"
                    path.write_text(stream.getvalue(), encoding="utf-8")
                    self.assertTrue(load_log(path)["capture"]["complete"])

    def test_start_cue_occurs_once_after_suback_and_never_on_failure(self):
        for behavior, expected in [("success", [0.5]), ("denied", []), ("timeout", [])]:
            clock, stream, cues = Clock(), io.StringIO(), []
            capture(stream, config(), schedule(), 8000, Client(clock, behavior), clock,
                    host="synthetic.invalid", connect_timeout=1, on_started=lambda: cues.append(clock()))
            self.assertEqual(cues, expected)

    def test_connection_subscription_disconnect_and_loop_errors_are_incomplete(self):
        for behavior in ["connect_error", "timeout", "denied", "disconnect", "loop_error"]:
            with self.subTest(behavior=behavior):
                end, parsed, elapsed = self.run_capture(behavior)
                self.assertFalse(end["complete"])
                self.assertFalse(parsed["capture"]["complete"])
                self.assertLessEqual(elapsed, 2)

    def test_duration_must_cover_schedule_and_sample_limit_stops_capture(self):
        clock, stream = Clock(), io.StringIO()
        with self.assertRaises(ValueError):
            capture(stream, config(), schedule(), 100, Client(clock), clock, host="synthetic.invalid")
        self.assertEqual(stream.getvalue(), "")
        with patch("tooling.calibration.capture.MAX_RECORDS", 2):
            end, parsed, _ = self.run_capture("success")
        self.assertEqual(end["reason"], "limit")
        self.assertEqual(len(parsed["records"]), 2)
        self.assertFalse(end["complete"])

    def test_capture_output_never_overwrites_existing_or_partial_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.jsonl"
            for existing in [output, output.with_name(output.name + ".partial")]:
                existing.write_text("original", encoding="utf-8")
                with self.assertRaises(ValueError):
                    capture_file(output, config(), schedule(), 8000)
                self.assertEqual(existing.read_text(), "original")
                existing.unlink()

    def test_output_created_during_capture_preserves_both_evidence_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.jsonl"
            partial = output.with_name(output.name + ".partial")

            def competing_writer(*args, **kwargs):
                partial.write_text(log_text([]), encoding="utf-8")
                output.write_text("concurrent evidence", encoding="utf-8")

            with patch("tooling.calibration.process.bounded_process", side_effect=competing_writer):
                with self.assertRaises(OSError):
                    capture_file(output, config(), schedule(), 8000)
            self.assertEqual(output.read_text(), "concurrent evidence")
            self.assertTrue(load_log(partial)["capture"]["complete"])

    def test_stalled_child_is_terminated_and_partial_file_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            started = time.monotonic()
            with self.assertRaises(ValueError):
                bounded_process(stalled_child, (str(path),), timeout=0.7)
            self.assertLess(time.monotonic() - started, 5)
            if path.exists():
                with self.assertRaises(ValueError):
                    load_log(path)


if __name__ == "__main__":
    unittest.main()
