# Pet advisory development and replay

Feature 002 is being delivered in reviewed slices. The domain model and offline
replay are the first slice. Home Assistant installation, package generation and
real runtime validation remain unchecked until their implementation is delivered.
Do not install the partial `custom_components` directory into production yet.

The complete feature combines fresh ESPresense observations, an exterior door
contact and camera evidence into advisory levels. BLE observations estimate room
proximity; a camera's `cat` label does not identify a particular animal. Neither
provides a physical containment guarantee. This software is an additional signal
for people supervising doors, not an automatic containment mechanism.

## Private configuration

Copy `examples/pet.example.json` outside the checkout. Replace fictional mappings
locally; never paste enrollment IRKs into this file or chat. `device_alias` is the
friendly enrolled ID used in ESPresense device topics. MQTT credentials remain
managed by Home Assistant, outside this configuration and all git repositories.

The schema configures one subject per Home Assistant instance:

| Field | Meaning |
|---|---|
| `schema` | Integer `1` |
| `pet_id` | Stable lowercase alias using underscores; used for entity identifiers |
| `name` | Short human-readable label |
| `device_alias` | Friendly enrolled MQTT device alias, never an IRK or MAC |
| `nodes` | 1–64 node aliases with actual `mqtt_room` slug and diagnostic `room` alias |
| `doors` | 1–16 door aliases with contact entity, node aliases and `exterior` boolean |
| `timing` | Optional explicit interval overrides in seconds |
| `frigate_topic` | Exact topic, default `frigate/events`; no wildcard |

Door IDs use lowercase letters, digits and underscores, beginning with a letter.
Each door has a `binary_sensor` contact entity and a nonempty list of mapped nodes.
Its optional `near_rssi_dbm` defaults to -65. Optional `camera`, `inside_zones` and
`outside_zones` map Frigate observations; inside/outside zones must be disjoint.
Without a camera map the door can provide proximity and heads-up evidence but cannot
initiate a camera-correlated incident. Internal doors never initiate escape advisories.
Names, maps, event histories and reports are private even when raw IDs are removed.

## Evidence rules

Only fresh finite observations from mapped indoor nodes count. Retained and malformed
MQTT messages are discarded. Identical new readings refresh their receipt time.
The minimum distance yields a room candidate; tied nodes in one room agree, while
ties between rooms remain unknown. Thirty seconds of continuing evidence accepts a
room. A single report followed by silence cannot satisfy the hold.

The default freshness interval is 20 seconds. Per-door proximity requires fresh RSSI
from that door's configured nodes. Missing local RSSI is unknown, even if a distant
node hears the target. Fresh local RSSI below the threshold means no current proximity
indication. It never proves absence. Thresholds require local measurements.

The last accepted room is retained for ten minutes after its last qualifying report.
A separate fifteen-minute recent-observation flag records history, not proof that the
animal is still indoors. These are distinct from continuous recovery evidence.

An actual closed-to-open exterior contact transition while near produces a heads-up,
with a default 60-second cooldown per door. A restored-open or unavailable contact
cannot invent a transition. Camera threshold evidence within 180 seconds after an
opening can latch Suspected. Outside-zone evidence can latch Urgent directly. Frame
time must follow that same door's opening; stale, future, ended, false-positive or
repeated zone observations do not qualify. Historical `entered_zones` is not used as
current occupancy. Missing upstream events remain missing evidence.

While Suspected, 180 seconds without credible indoor evidence during continuous
monitoring can raise Urgent. Broker loss interrupts that interval and preserves the
latch; reconnecting starts a full monitored interval. Unobserved downtime is never
counted as confirmed silence. Radio silence alone cannot initiate an escape incident.

Acknowledgement records that an operator saw the incident; it does not clear it.
Sixty seconds of new, continuing stable indoor evidence after the incident clears
and re-arms it. Gaps, contradictions and outages reset recovery. Independently
correlated incidents at other doors may raise severity; all affected doors remain
marked until recovery. Escalation resets acknowledgement.

Only incident state and bounded camera deduplication history survive restart.
Freshness, candidates, proximity and recovery do not. Deduplication retains 256
event/door/stage entries; this is finite history, not an indefinite replay guarantee.
Timestamp validation separately rejects stale frames. Thirty minutes of monitored
silence can produce a collar-health advisory once per silence episode, never an
escape inference. A valid observation resets that health episode.

Door intent is red while affected by a latched incident, blue while near, off when
fresh local evidence is below threshold, and unknown without usable local evidence.
The eventual output package sends no preset change for unknown. WLED presets and
operator scripts own brightness/night schedules. Scanner status LEDs are unchanged.

## Offline replay

From the checkout, use a private directory that already exists:

```powershell
python -m tooling.pet replay --config examples/pet.example.json --events examples/pet.events.example.jsonl --output <private-directory>/pet-replay.json
```

The command contacts no devices and delivers no notifications or light changes.
It writes deterministic state snapshots and advisory intents. Invalid input exits
nonzero without printing raw input or replacing a previous report. Successful replay
can replace its previous output report, but cannot overwrite either input file.

Each JSONL event has integer `schema: 1`, a `kind` and nondecreasing `elapsed_s`
between zero and 86400. Limits are 10000 events, 8192 characters per line and 32MiB.
Unknown fields and duplicate JSON keys are rejected.

| Kind | Additional fields |
|---|---|
| `transport` | Boolean `connected` |
| `observation` | `node`, finite `distance_m`, optional `rssi_dbm`, optional boolean `retained` |
| `door_open` | `door`; represents an already validated physical closed-to-open transition |
| `camera` | `door`, `zone` (`inside` or `outside`), `event_id`, `evidence_at_s`, optional `retained` |
| `acknowledge` | None |
| `tick` | None; advances timers without creating a radio observation |
| `restart` | None; restores persistent incident state into an unavailable fresh runtime |

Camera replay events are already normalized: the real ingress separately filters
Frigate frame timestamps and newly entered current zones. Reports omit the friendly
wire device selector and raw event IDs. Replay proves the supplied scenario's
software behavior, not that an actual walk, door opening or alert delivery occurred.

## Remaining installation and acceptance

The HA adapter and package must pass pinned-runtime checks before installation is
documented as available. Then verify private contact/node/camera mappings, fit and
test the collar, measure thresholds, and stage a supervised doorway exercise. Test
notification and light delivery explicitly before enabling outputs. Confirm restart,
disconnect, acknowledgement and recovery behavior on the actual installation.

Record physical evidence privately under the setup checklist. See
[spec 002](../specs/002-pet-safety/spec.md) and its
[tasks](../specs/002-pet-safety/tasks.md); unchecked work is not implied complete.
