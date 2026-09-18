"""Deterministic nearest-node windows and directional radio survey summaries."""
from bisect import bisect_left
from collections import defaultdict
from statistics import median

from .records import validate_schedule

LIMITS = ("Receiver timing is not transmission timing; delayed non-retained data may be stale. "
          "Nearest-node diagnostics are not Companion positioning. Silence is not absence. "
          "This report establishes no whole-home coverage or pet-safety guarantee.")


def base_report(log, schedule, diagnostic):
    validate_schedule(schedule)
    nodes = schedule["nodes"]
    for row in log["records"]:
        if row["node"] not in nodes or ("peer" in row and row["peer"] not in nodes):
            raise ValueError("Evidence references unmapped nodes")
    return {"schema": 1, "scoring_version": "1.0", "diagnostic": diagnostic,
            "parameters": schedule, "capture": log["capture"], "limitations": LIMITS}


def window_result(rows, stop, start, end, complete, nodes):
    distances = defaultdict(list)
    for row in rows:
        distances[row["node"]].append(row["distance_m"])
    medians = {node: median(values) for node, values in sorted(distances.items())}
    winners = [node for node, value in medians.items() if value == min(medians.values())]
    status = "no_data" if not winners else "winner" if len(winners) == 1 else "ambiguous"
    winner = winners[0] if len(winners) == 1 else None
    room = nodes[winner] if winner else None
    return {"start_ms": start, "end_ms": end, "expected_room": stop["room"],
            "status": status if complete else "incomplete", "observed_status": status,
            "samples": len(rows), "observed_nodes": sorted(medians), "medians_m": medians,
            "samples_per_node": {node: len(values) for node, values in sorted(distances.items())},
            "expected_room_samples": sum(len(values) for node, values in distances.items() if nodes[node] == stop["room"]),
            "winning_node": winner, "winning_room": room,
            "mismatch": room != stop["room"] if room and complete else None}


def score(log, schedule):
    report = base_report(log, schedule, "nearest_node")
    rows = [row for row in log["records"] if row["kind"] == "device"]
    times = [row["elapsed_ms"] for row in rows]
    groups = []
    flip_pairs, false_flips = 0, 0
    width = schedule["window_ms"]
    observed_end = log["capture"]["elapsed_ms"]
    for stop in schedule["stops"]:
        windows = []
        for start in range(stop["start_ms"], stop["end_ms"], width):
            end = min(start + width, stop["end_ms"])
            selected = rows[bisect_left(times, start):bisect_left(times, end)]
            windows.append(window_result(selected, stop, start, end,
                                         end - start == width and end <= observed_end,
                                         schedule["nodes"]))
        for old, new in zip(windows, windows[1:]):
            if old["status"] == new["status"] == "winner":
                flip_pairs += 1
                false_flips += old["winning_room"] != new["winning_room"]
        groups.append(windows)
    transitions = []
    for old, new in zip(groups, groups[1:]):
        before, after = old[-1], new[0]
        valid = before["status"] == after["status"] == "winner"
        if before["expected_room"] == after["expected_room"]:
            status = "same_room"
        elif not valid:
            status = "indeterminate"
        else:
            status = "clean" if not before["mismatch"] and not after["mismatch"] else "mismatch"
        transitions.append({"from_room": before["expected_room"], "to_room": after["expected_room"],
                            "gap_ms": after["start_ms"] - before["end_ms"],
                            "status": status})
    windows = [window for group in groups for window in group]
    evaluated = sum(w["status"] == "winner" for w in windows)
    matched = sum(w["mismatch"] is False for w in windows)
    all_pairs = sum(max(0, len(group) - 1) for group in groups)
    report.update(windows=windows, transitions=transitions,
                  summary={"total_windows": len(windows), "evaluated_windows": evaluated,
                           "matched_windows": matched, "mismatches": evaluated - matched,
                           "matched_fraction_all_windows": matched / len(windows),
                           "no_data_windows": sum(w["status"] == "no_data" for w in windows),
                           "ambiguous_windows": sum(w["status"] == "ambiguous" for w in windows),
                           "incomplete_windows": sum(w["status"] == "incomplete" for w in windows),
                           "false_flips": false_flips, "false_flip_pairs_evaluated": flip_pairs,
                           "false_flip_pairs_total": all_pairs, "false_flip_pair_gaps": all_pairs - flip_pairs,
                           "transitions_total": sum(t["status"] != "same_room" for t in transitions),
                           "transitions_evaluated": sum(t["status"] in ("clean", "mismatch") for t in transitions),
                           "walking_gap_ms": sum(t["gap_ms"] for t in transitions)})
    report["nodes"] = {}
    for node in sorted(schedule["nodes"]):
        distances = [row["distance_m"] for row in rows if row["node"] == node]
        report["nodes"][node] = {"status": "observed" if distances else "no_data", "samples": len(distances),
                                 "minimum_m": min(distances) if distances else None,
                                 "review_minimum_never_below_3m": min(distances) >= 3 if distances else None}
    report["heuristics"] = {"minimum_distance_review_m": 3, "automatic_calibration": False}
    return report


def coverage(log, schedule):
    report = base_report(log, schedule, "radio_survey")
    nodes = sorted(schedule["nodes"])
    wifi, pairs = defaultdict(list), defaultdict(list)
    for row in log["records"]:
        if row["kind"] == "wifi":
            wifi[row["node"]].append(row["rssi_dbm"])
        if row["kind"] == "node_distance":
            pairs[(row["node"], row["peer"])].append(row["distance_m"])
    report.update(wifi={}, pairs={}, router_separation={})
    for node in nodes:
        values = wifi[node]
        report["wifi"][node] = {"status": "observed" if values else "no_data", "samples": len(values),
                                "median_dbm": median(values) if values else None,
                                "minimum_dbm": min(values) if values else None,
                                "samples_below_minus70_dbm": sum(v < -70 for v in values),
                                "review": min(values) < -70 if values else None}
        measured = schedule.get("router_separation_m", {}).get(node)
        report["router_separation"][node] = {"status": "operator_measured" if measured is not None else "not_measured",
                                            "distance_m": measured, "review": measured < 2 if measured is not None else None}
        for peer in nodes:
            if peer == node:
                continue
            values = pairs[(node, peer)]
            report["pairs"][f"{node}->{peer}"] = {"status": "observed" if values else "no_data", "samples": len(values),
                                                   "median_m": median(values) if values else None}
    report["missing_pairs"] = sum(p["status"] == "no_data" for p in report["pairs"].values())
    report["heuristics"] = {"wifi_review_below_dbm": -70, "operator_router_separation_below_m": 2,
                             "direction": "node receives peer", "physical_distance_inferred": False}
    return report
