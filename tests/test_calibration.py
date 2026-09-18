"""Synthetic diagnostic evidence: no household or transport identifiers."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tooling.calibration.records import load_log, validate_schedule
from tooling.calibration.scoring import score, coverage

ROOT = Path(__file__).resolve().parents[1]


def schedule():
    return {"schema": 1, "window_ms": 1000,
            "nodes": {"node01": "room01", "node02": "room02", "node03": "room01"},
            "stops": [{"room": "room01", "start_ms": 0, "end_ms": 4000},
                      {"room": "room02", "start_ms": 5000, "end_ms": 7500}]}


def record(time, node="node01", distance=1, **extra):
    return dict(schema=1, kind="device", elapsed_ms=time, node=node,
                distance_m=distance, **extra)


def log_text(records, complete=True):
    start = dict(schema=1, kind="capture_start", source="synthetic", duration_ms=8000)
    end = dict(schema=1, kind="capture_end", elapsed_ms=8000, records=len(records),
               complete=complete, reason="duration" if complete else "disconnect",
               retained=0, ignored=0, invalid=0)
    return "\n".join(json.dumps(row) for row in [start, *records, end]) + "\n"


def load_rows(rows, complete=True):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "walk.jsonl"
        path.write_text(log_text(rows, complete), encoding="utf-8")
        return load_log(path)


class CalibrationTests(unittest.TestCase):
    def test_wrong_plateau_missing_tie_and_incomplete_are_not_success(self):
        rows = [record(0, "node02"), record(999, "node01", 4),
                record(1000, "node02"), record(3000), record(3000, "node02"),
                record(5000, "node02"), record(6000, "node02"), record(7000, "node02")]
        report = score(load_rows(rows), validate_schedule(schedule()))
        self.assertEqual([w["status"] for w in report["windows"]],
                         ["winner", "winner", "no_data", "ambiguous", "winner", "winner", "incomplete"])
        self.assertEqual(report["summary"]["mismatches"], 2)
        self.assertEqual(report["summary"]["matched_windows"], 2)
        self.assertEqual(report["summary"]["total_windows"], 7)
        self.assertEqual(report["summary"]["false_flips"], 0)
        self.assertEqual(report["transitions"][0]["status"], "indeterminate")
        self.assertEqual(report["nodes"]["node03"]["status"], "no_data")

    def test_median_winners_half_open_false_flips_and_clean_transition(self):
        data = schedule()
        data["stops"][0]["end_ms"] = 3000
        data["stops"][1]["end_ms"] = 7000
        rows = [record(0, distance=1), record(10, distance=100), record(20, distance=2),
                record(30, "node02", 3), record(1000, "node02"), record(2000),
                record(3000, "node02"), record(5000, "node02"), record(6000, "node02")]
        report = score(load_rows(rows), validate_schedule(data))
        self.assertEqual(report["windows"][0]["medians_m"]["node01"], 2)
        self.assertEqual(report["summary"]["false_flips"], 2)
        self.assertEqual(report["summary"]["false_flip_pairs_evaluated"], 3)
        self.assertEqual(report["transitions"][0]["status"], "clean")
        self.assertEqual(report["summary"]["walking_gap_ms"], 2000)

    def test_capture_incomplete_propagates_and_retained_is_excluded(self):
        report = score(load_rows([record(0, retained=True)], False), schedule())
        self.assertFalse(report["capture"]["complete"])
        self.assertEqual(report["capture"]["retained"], 1)
        self.assertEqual(report["windows"][0]["status"], "no_data")

    def test_missing_boundary_does_not_bridge_last_valid_window(self):
        data = schedule()
        data["stops"][0]["end_ms"] = 3000
        rows = [record(0), record(1000), record(5000, "node02")]
        report = score(load_rows(rows), data)
        self.assertEqual(report["transitions"][0]["status"], "indeterminate")
        self.assertEqual(report["summary"]["false_flip_pair_gaps"], 3)

    def test_capture_bounds_and_metadata_cannot_claim_missing_time(self):
        for change in [{"elapsed_ms": 8001}, {"complete": True, "reason": "disconnect"},
                       {"elapsed_ms": 7999}, {"records": True}, {"extra": "private"}]:
            content = log_text([]).splitlines()
            end = json.loads(content[-1])
            end.update(change)
            content[-1] = json.dumps(end)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "log.jsonl"
                path.write_text("\n".join(content), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_log(path)
        with self.assertRaises(ValueError):
            load_rows([record(8000)])

    def test_same_room_boundary_is_not_a_clean_room_transition(self):
        data = schedule()
        data["stops"] = [{"room": "room01", "start_ms": 0, "end_ms": 1000},
                         {"room": "room01", "start_ms": 2000, "end_ms": 3000}]
        report = score(load_rows([record(0), record(2000)]), data)
        self.assertEqual(report["transitions"][0]["status"], "same_room")
        self.assertEqual(report["summary"]["transitions_total"], 0)

    def test_bad_records_and_metadata_fail_without_echoing_raw(self):
        base = record(0)
        for change in [{"distance_m": -1}, {"distance_m": True}, {"distance_m": float("nan")}, {"distance_m": 10 ** 400},
                       {"elapsed_ms": -1}, {"rssi_dbm": False}, {"schema": True},
                       {"kind": "secret-value"}, {"name": "secret-value"}, {"node": "secret:value"}]:
            with self.subTest(change=change), self.assertRaises(ValueError) as error:
                load_rows([dict(base, **change)])
            self.assertNotIn("secret-value", str(error.exception))
        with self.assertRaises(ValueError):
            load_rows([record(2), record(1)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            for content in [log_text([]).splitlines()[0], log_text([]).replace('"records": 0', '"records": 1'), "{secret-value"]:
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_log(path)

    def test_schedule_rejects_overlap_nonfinite_booleans_and_unknown_nodes(self):
        for change in [lambda s: s.update(window_ms=True), lambda s: s.update(window_ms=float("inf")),
                       lambda s: s["stops"][1].update(start_ms=3999),
                       lambda s: s["stops"][0].update(room="room99"),
                       lambda s: s.update(extra="private")]:
            data = schedule()
            change(data)
            with self.assertRaises(ValueError):
                validate_schedule(data)
        with self.assertRaises(ValueError):
            score(load_rows([record(0, "node99")]), schedule())

    def test_coverage_directionality_and_measured_router_separation(self):
        rows = [dict(schema=1, kind="wifi", elapsed_ms=0, node="node01", rssi_dbm=-80),
                dict(schema=1, kind="wifi", elapsed_ms=1, node="node01", rssi_dbm=-60),
                dict(schema=1, kind="node_distance", elapsed_ms=2, node="node01", peer="node02", distance_m=4),
                dict(schema=1, kind="node_distance", elapsed_ms=3, node="node02", peer="node01", distance_m=7)]
        data = schedule()
        data["router_separation_m"] = {"node01": 1.5}
        report = coverage(load_rows(rows), validate_schedule(data))
        self.assertEqual(report["wifi"]["node01"]["median_dbm"], -70)
        self.assertEqual(report["wifi"]["node02"]["status"], "no_data")
        self.assertEqual(report["pairs"]["node01->node02"]["median_m"], 4)
        self.assertEqual(report["pairs"]["node02->node01"]["median_m"], 7)
        self.assertEqual(report["missing_pairs"], 4)
        self.assertTrue(report["router_separation"]["node01"]["review"])
        self.assertEqual(report["router_separation"]["node02"]["status"], "not_measured")

    def test_real_cli_replay_is_deterministic_and_redacts_parse_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "walk.jsonl").write_text(log_text([record(0, "node02")]), encoding="utf-8")
            (folder / "schedule.json").write_text(json.dumps(schedule()), encoding="utf-8")
            for command in ["score", "coverage"]:
                args = [sys.executable, "-m", "tooling.calibration", command, "--log", str(folder / "walk.jsonl"),
                        "--schedule", str(folder / "schedule.json"), "--output", str(folder / "report.json")]
                first = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(first.returncode, 0, first.stderr)
                output = (folder / "report.json").read_bytes()
                self.assertEqual(subprocess.run(args, cwd=ROOT, capture_output=True).returncode, 0)
                self.assertEqual(output, (folder / "report.json").read_bytes())
            (folder / "walk.jsonl").write_text('secret-value', encoding="utf-8")
            failed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertNotIn("secret-value", failed.stdout + failed.stderr)

    def test_huge_json_numbers_fail_cli_without_tracebacks_or_data(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for malformed_schedule in (False, True):
                data = schedule()
                if malformed_schedule:
                    data["window_ms"] = 10 ** 400
                (folder / "schedule.json").write_text(json.dumps(data), encoding="utf-8")
                (folder / "walk.jsonl").write_text(log_text([record(0, distance=10 ** 400)]), encoding="utf-8")
                result = subprocess.run([sys.executable, "-m", "tooling.calibration", "score",
                                         "--schedule", str(folder / "schedule.json"), "--log", str(folder / "walk.jsonl"),
                                         "--output", str(folder / "report.json")], cwd=ROOT, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn(str(10 ** 400), result.stderr)


if __name__ == "__main__":
    unittest.main()
