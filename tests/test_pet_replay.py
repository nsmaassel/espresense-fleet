import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReplayTests(unittest.TestCase):
    def config(self):
        return {"schema": 1, "pet_id": "example_pet", "name": "Example Pet",
                "device_alias": "example-collar",
                "nodes": {"node_a": {"mqtt_room": "example-a", "room": "room_a"}},
                "doors": {"entry": {"contact": "binary_sensor.example_entry", "nodes": ["node_a"],
                                    "exterior": True, "near_rssi_dbm": -65, "camera": "example-camera",
                                    "inside_zones": ["threshold"], "outside_zones": ["walkway"]}}}

    def run_cli(self, folder, events):
        (folder / "config.json").write_text(json.dumps(self.config()), encoding="utf-8")
        (folder / "events.jsonl").write_text("\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
        return subprocess.run([sys.executable, "-m", "tooling.pet", "replay", "--config", str(folder / "config.json"),
                               "--events", str(folder / "events.jsonl"), "--output", str(folder / "report.json")],
                              cwd=ROOT, capture_output=True, text=True, timeout=10)

    def test_actual_cli_replays_latch_ack_recovery_deterministically(self):
        def event(kind, elapsed, **data):
            return dict(schema=1, kind=kind, elapsed_s=elapsed, **data)
        rows = [event("transport", 0, connected=True)]
        rows += [event("observation", t, node="node_a", distance_m=1, rssi_dbm=-60) for t in (1, 10, 20, 31)]
        rows += [event("door_open", 32, door="entry"),
                 event("camera", 33, door="entry", zone="inside", event_id="synthetic-event", evidence_at_s=33),
                 event("acknowledge", 34)]
        rows += [event("observation", t, node="node_a", distance_m=1, rssi_dbm=-60) for t in range(40, 101, 10)]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            first = self.run_cli(folder, rows)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = (folder / "report.json").read_bytes()
            report = json.loads(original)
            levels = [intent["level"] for row in report["snapshots"] for intent in row["intents"]]
            self.assertEqual(levels, ["heads_up", "suspected", "recovered"])
            self.assertEqual(report["snapshots"][7]["state"]["alert"]["level"], "suspected")
            self.assertTrue(report["snapshots"][7]["state"]["alert"]["acknowledged"])
            self.assertEqual(report["snapshots"][-1]["state"]["alert"]["level"], "clear")
            self.assertEqual(self.run_cli(folder, rows).returncode, 0)
            self.assertEqual((folder / "report.json").read_bytes(), original)
            self.assertNotIn(b"synthetic-event", original)
            self.assertNotIn(b"example-collar", original)

    def test_invalid_input_never_replaces_previous_report_or_echoes_payload(self):
        for row in ({"schema": 1, "kind": "leak-marker", "elapsed_s": 0},
                    {"schema": 1, "kind": "transport", "elapsed_s": True, "connected": True},
                    {"schema": 1, "kind": "transport", "elapsed_s": 0, "connected": "leak-marker"}):
            with self.subTest(kind=row["kind"]), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                (folder / "report.json").write_text("preserve", encoding="utf-8")
                result = self.run_cli(folder, [row])
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("leak-marker", result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual((folder / "report.json").read_text(), "preserve")

    def test_documented_fixture_survives_restart_without_restoring_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = subprocess.run([sys.executable, "-m", "tooling.pet", "replay",
                                     "--config", "examples/pet.example.json",
                                     "--events", "examples/pet.events.example.jsonl",
                                     "--output", str(output)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = json.loads(output.read_text())["snapshots"]
            restarted = next(row for row in rows if row["event"] == "restart")["state"]
            self.assertEqual(restarted["alert"]["level"], "suspected")
            self.assertTrue(restarted["alert"]["acknowledged"])
            self.assertIsNone(restarted["room"])
            self.assertIsNone(restarted["last_seen_age_s"])
            self.assertEqual(restarted["health"], "transport_unavailable")
            self.assertEqual(rows[-1]["state"]["alert"]["level"], "clear")


if __name__ == "__main__":
    unittest.main()
