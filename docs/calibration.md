# Calibration and coverage evidence

Use this diagnostic after mounting, provisioning and enrolling the target device.
The operator supplies a timed stationary-stop schedule and performs the walk.
This delivery scores normalized observations from saved logs. Live recording is
the next delivery.
It never changes node settings, calibration RSSI, optimizer bounds or placement.
This is a nearest-node diagnostic, not ESPresense Companion's position estimator.

## Offline rehearsal

Python 3.11+ is enough for replay; no broker or optional packages are needed.
Both example files are invented documentation fixtures, never household data.
The example deliberately includes ties, missing observations and wrong winners.
Choose a private output directory **outside this checkout** and create it first:

```powershell
python -m tooling.calibration score --log examples/calibration.walk.example.jsonl --schedule examples/calibration.schedule.example.json --output <private-directory>/walk-report.json
python -m tooling.calibration coverage --log examples/calibration.walk.example.jsonl --schedule examples/calibration.schedule.example.json --output <private-directory>/survey-report.json
```

Outputs are JSON with `schema: 1`, `scoring_version: "1.0"`, the complete schedule,
capture metadata, parameters and limitations. The console gives a brief readable
summary. Identical files produce identical reports. A valid diagnostic with
mismatches or no observations exits zero; invalid input or capture failure exits
nonzero. A partial capture with a valid footer can be replayed, but stays explicitly
`complete: false`. A truncated file without its footer fails validation.

## Prepare the walk

Copy the schedule example into private storage. Map each node
to a short alias, then map that alias to a room in the schedule. Labels may use
lowercase letters, digits, underscores and hyphens, start with a letter, and have
at most 48 characters. Use neutral aliases where possible. Raw addresses,
credential-shaped strings and `irk` prefixes are rejected. Even minimized logs,
aliases, schedules and reports remain private: room names and timing can identify
a household. Keep credentials outside every repository; never paste them into chat.

Schedule fields:

| Field | Meaning |
|---|---|
| `schema` | Integer `1` |
| `window_ms` | Integer 100–60000; 5000–10000 is a practical starting choice |
| `nodes` | 1–64 output node aliases mapped to room aliases |
| `stops` | 1–200 ordered nonoverlapping `{room,start_ms,end_ms}` intervals |
| `router_separation_m` | Optional alias-to-measured-distance map; omit unmeasured nodes |

Times are integer milliseconds from the recorded start, between 0 and 3600000.
Stops must have positive duration and a room with a mapped node. Gaps are walking;
their device samples do not belong to a stationary window. At most 10000 windows
are accepted. Router separation is the operator's separately measured distance to
the nearest relevant Wi-Fi router/AP, from 0–1000m. It is never estimated from RSSI.
The example measurements are fictional; replace them or omit the field.

For the example schedule, stand at room01 before starting. At recorded time zero remain
there for 20 seconds, walk for 5 seconds, remain at room02 for 20 seconds, walk for
5 seconds, then remain at room01 for 20 seconds. Adjust this schedule to an honest
record of the route. Actual pairing, mounting and walking require the operator.

## Capture delivery

This delivery provides offline `score` and `coverage` commands. Bounded live MQTT
capture and its transport tests are the next delivery of spec 005. The normalized
contract below already supports completeness metadata for replay.

## JSONL contract

One JSON object per line, UTF-8. Unknown fields, duplicate keys, unsupported schemas,
malformed JSON, booleans as numbers, nonfinite numbers and out-of-order timestamps
are rejected. Limits: 64MiB, 200000 observations, 4096 characters per normalized line.
The first and last lines are mandatory:

```json
{"schema":1,"kind":"capture_start","source":"mqtt","duration_ms":70000}
{"schema":1,"kind":"device","elapsed_ms":12,"node":"node01","distance_m":1.4,"rssi_dbm":-62}
{"schema":1,"kind":"wifi","elapsed_ms":20,"node":"node01","rssi_dbm":-68}
{"schema":1,"kind":"node_distance","elapsed_ms":31,"node":"node01","peer":"node02","distance_m":4.2}
{"schema":1,"kind":"capture_end","elapsed_ms":70000,"records":3,"complete":true,"reason":"duration","retained":0,"ignored":0,"invalid":0}
```

The snippet illustrates structure only. Three samples cannot establish a route's
coverage. `source` is `mqtt` or `synthetic`. Observation timestamps are nondecreasing
integers in `[0,duration_ms)`. Distance is finite 0–10000m; RSSI is finite -200–0dBm.
`rssi_dbm` is optional for device observations and required for Wi-Fi observations.
A directional record means **node receives peer** and cannot refer to itself.
Replay accepts only those normalized fields and rejects extras. The capture
contract requires dropping incoming name, MAC, IP, topic, raw device ID,
advertisement interval and unrelated payload fields before persistence.
Malformed approved payloads are counted as `invalid`; other topics as `ignored`.
Neither count is silently turned into evidence of reception.

Replay observations may also contain boolean `retained`; true excludes the entire
observation and adds to the retained count. The live capture contract excludes retained messages
before writing records. Footer `records` counts serialized observations, including
any retained observations supplied in a replay file. Footer `retained` counts
messages excluded before serialization, so these counts do not overlap.
`ignored`, `invalid` and `retained` are nonnegative integers. On capture, reaching
200000 observations or one million total processed messages stops with `limit`.

Footer elapsed time must lie within the requested duration and follow the last
record. `complete: true` requires elapsed time equal to duration and `reason:
"duration"`. Other reasons (`connection`, `subscription`, `disconnect`, `transport`,
`limit`, `interrupted`) require `complete: false`. Counts must match the actual file;
data after the footer is rejected. Completion means the capture ran for its requested
duration, **not** that the walk happened or that all nodes heard the device.

## Interpret the report

Windows are half-open `[start,end)`, anchored independently at each stop. Each node
gets a median from its samples within that window only. The unique smallest median
wins. Equal medians are ambiguous even if the tied nodes map to the same room.
No samples means no-data; no earlier distance is carried forward. A final short
window or one extending beyond capture time is incomplete. Its observed candidate
is shown, but it does not enter the evaluated-winner denominator.

The report includes node sample counts, nodes observed, expected-room samples,
winning node/room, and mismatches. A stable wrong room remains a mismatch. The
matched fraction uses **all scheduled windows**, including missing, ambiguous and
incomplete windows. False flips compare only adjacent valid winning-room windows
within one stop; missing evidence breaks adjacency. Evaluated and total pair counts
show how much evidence supports that count.

A clean room transition requires the actual final old-stop window and actual first
new-stop window to both match their expected rooms. Missing, ambiguous or incomplete
boundary windows are indeterminate; the scorer never searches backward for a usable
window. Adjacent stops in the same room are labeled `same_room` and excluded from
room-transition denominators. Walking-gap time is reported, not scored as stationary
evidence; these diagnostics do not measure the precise moment of a room crossing.

Per-node target-distance minima include the entire capture, including walking.
A minimum never below 3m is a placement/calibration **review heuristic**, not proof
of an error and not an automatic signed RSSI correction. No samples is no-data.
Survey output reports Wi-Fi medians, minimum RSSI, sample counts and samples below
-70dBm. Any such sample triggers a review heuristic. Separately measured router/AP
separation below 2m triggers its own warning; missing measurement stays unmeasured.
All ordered node pairs are reported, including missing directions. BLE estimates
from A receiving B and B receiving A are never averaged into physical separation.

The pinned [ESPresense v4.0.6 publisher](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/main.cpp)
sends device messages at `espresense/devices/<id>/<node-slug>` and Wi-Fi telemetry at
`espresense/rooms/<node-slug>/telemetry` (at least 15 seconds apart).
The [device payload](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/BleFingerprint.cpp)
contains `distance` and `rssi`; `int` is advertisement interval, not an observation
timestamp. [Self-beacon mappings](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/Enrollment.cpp)
use `node:<slug>`. Retained online status is never freshness evidence.

Receiver timing cannot rule out delayed non-retained packets. Reporting filters,
body occlusion and lost reception can cause silence. The schedule is supplied ground
truth, not proof of the walk. Short synthetic replays establish software behavior;
real Wi-Fi, room coverage, closed-door reception and collar performance remain
physical acceptance work. No whole-home accuracy or pet-safety claim follows from
this report.
