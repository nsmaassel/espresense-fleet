# Spec 005: Calibration and coverage evidence

**Status:** Software implemented and independently reviewed; CI validation is the merge gate. Physical walks remain deferred.
**Tracks:** Issue #6; foundation US4/US5.

## User stories

An operator records a walk for an enrolled device, supplies the stationary stop
schedule, and reruns an offline scorer to see observed winners, mismatches,
false flips and missing evidence. A survey reports Wi-Fi and directional BLE
observations without claiming that radio estimates prove physical geometry.

## Requirements

- **FR-001**: Read versioned allowlisted JSONL with receiver-relative `elapsed_ms`, neutral node aliases and finite numeric observations. Device records contain `kind: device`, `node`, `distance_m` and optional `rssi_dbm`; Wi-Fi records contain `kind: wifi`, `node`, `rssi_dbm`; directional node observations contain `kind: node_distance`, `node`, `peer`, `distance_m`. Reject booleans as numbers, negative time/distances, unknown schema/kinds, malformed records and nonmonotonic timestamps without echoing raw lines. Retained observations are excluded and counted.
- **FR-002**: Validate an external JSON schedule (`schema: 1`, `window_ms`, `nodes` alias-to-room map, and `stops` with `room`, `start_ms`, `end_ms`). Stops are nonoverlapping stationary intervals; gaps are walking. Inputs/thresholds are bounded finite values. Windows are half-open and anchored at each stop; incomplete windows remain explicit.
- **FR-003**: For each window, compute per-node median distance from only samples received inside that window. The unique smallest median identifies a winner; ties are ambiguous, absent samples are no-data. Do not carry values forward. Report samples, observed nodes, expected room evidence, winning room and mismatch. Missing windows do not improve success rates.
- **FR-004**: Count false flips only between adjacent valid winning-room windows within one stop. A stable wrong winner is still a mismatch. Score a transition only from the actual last window of the old stop and first window of the next; missing/ambiguous/incomplete boundary evidence is indeterminate, never silently bridged. Report evaluated/total denominators and gap counts.
- **FR-005**: Report per-node minimum observed target distance and observations; no samples is no-data. A minimum never below 3m is a heuristic for placement/calibration review, not an automatic signed RSSI correction. Reports include schema/scoring versions and parameters and make no whole-home or pet-safety success claim.
- **FR-006**: Capture only approved topic shapes for one enrolled device alias and explicitly mapped nodes, add receiver monotonic elapsed time, and persist only normalized fields. Drop raw IDs/MAC/name/IP/topics and deeper sub-report topics. Reject IRK-shaped/raw credential selectors; credentials come from a human's environment or secure local file, never CLI password arguments. Retained observations are excluded. Bound duration and network shutdown and handle disconnect/error honestly.
- **FR-007**: Survey scoring reports per-node Wi-Fi median/minimum RSSI with sample counts and directional node-to-node medians/missing pairs. RSSI below -70dBm is a documented heuristic. Router separation warnings below 2m require separately supplied operator measurements; infer neither physical distance nor router placement from RSSI or BLE range estimates.
- **FR-008**: Expose reproducible `python -m tooling.calibration score`, `capture` and `coverage` commands, JSON reports to an explicit external output path and readable summaries. Exit nonzero on input/capture failures; observed mismatches are data in a valid report, not parser failures. Never echo raw invalid data or secrets in errors. Logs/reports stay private even after field minimization.
- **FR-009**: Test actual CLI replay and deterministic scoring with synthetic multi-node schedules, ties, missing windows, half-open boundaries, wrong-room plateaus, retained data, out-of-order time, malformed/nonfinite data, and directional survey gaps. Test capture adapter topic normalization and bounded failure without real devices or credentials. Keep physical acceptance unchecked.

## Source contract

Normalized logs require a `capture_start` header with requested duration/source and
a `capture_end` footer with actual elapsed time, completeness, reason and counters.
Missing footers fail replay. A valid incomplete footer remains visibly incomplete
in reports. Completion requires the full requested duration; it proves neither
reception by every node nor that the operator followed the walk schedule.
Adjacent same-room stops are excluded from room-transition denominators.
Bounds are one hour, 64 nodes, 200 stops, 10000 windows, 200000 observations and
64MiB per normalized log. Optional Paho MQTT 2.1.0 is used only for capture.

Pinned ESPresense v4.0.6 sends non-retained device observations to
`espresense/devices/<id>/<node-slug>` with `distance`, `rssi` and calibration fields;
there is no observation timestamp. `int` is advertisement interval, not time.
Telemetry at `espresense/rooms/<node-slug>/telemetry` includes Wi-Fi `rssi` at
intervals of at least 15 seconds. Retained online status is not fresh evidence.
Self-beacons can be mapped as `node:<slug>`; those distances are directional.

Sources: [publish and telemetry](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/main.cpp),
[payload and distance math](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/BleFingerprint.cpp),
[self-beacon mappings](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/Enrollment.cpp).

## Limits and human work

Capture timestamps describe receipt, not radio transmission; delayed non-retained
messages may still be stale. Silence can reflect reporting filters or lost reception,
not absence. A schedule is supplied ground truth, not proof of the walk. This is a
nearest-node diagnostic, not Companion's locator. Actual placement, walk timing,
Wi-Fi reception and collar performance require the operator tomorrow.
