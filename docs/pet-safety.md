# Pet advisories: configuration, replay and Home Assistant

Feature 002 provides a pure advisory engine, offline replay, a Home Assistant custom
integration and a private package generator. The integration targets HA 2026.9.2.
Physical validation and live activation remain operator tasks.

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
The output package sends no preset change for unknown. WLED presets and
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

## Generate a private package

Copy `examples/pet.bindings.example.json` beside your private configuration. Its
integer `schema` is `1`. Both `notifications` and `lights` are optional; omitting
them creates no output automations. Notification keys are `heads_up`, `suspected`,
`urgent`, `health` and `recovered`, each bound to an existing `script.*` entity.
Light keys are configured door IDs. Each binding supplies a `light_entity`, a
`preset_entity` (`select.*`), and exact `off`, `blue`, `red` option names. Use plain
text, never Jinja templates. Create and verify those WLED presets separately.

```powershell
python -m tooling.pet package --config <private-directory>/pet.json --bindings <private-directory>/pet-bindings.json --output <private-directory>/pet-package.yaml
```

The generator writes deterministic YAML outside the checkout and refuses to replace
either input. It does not install anything or contact HA. Successful regeneration
replaces the previous package; keep custom scripts in a separate private package.
Avoid duplicate configuration for this integration or generated helper IDs.

## Install after reviewing the private mappings

1. Back up the HA configuration. Copy `custom_components/espresense_pet/` into the
   HA configuration directory's `custom_components/espresense_pet/` directory.
2. Put the generated package in a private `packages/` directory under HA's config.
   Merge `packages: !include_dir_named packages` into the existing `homeassistant:`
   section in `configuration.yaml`; do not create a second section.
3. Configure HA's MQTT integration through HA, with its existing broker credentials.
   Confirm exact device/node topics and the configured Frigate event topic.
4. Create the private notification scripts and WLED presets referenced by bindings.
   Run HA's configuration check, then restart HA. This is installation guidance;
   repository tests and generation do not perform these production actions.
5. Inspect the entities below, MQTT health and HA logs. Outputs start **off on every
   restart**, even if they were previously enabled. Leave them off during mapping
   and evidence validation. Turn them on only during supervised output acceptance.

For `pet_id: example_pet`, generated identifiers include:

| Entity | Meaning |
|---|---|
| `sensor.example_pet_room` | Currently qualified room, otherwise unknown |
| `sensor.example_pet_last_room` | Bounded last-room history |
| `binary_sensor.example_pet_recently_seen` | Recent observation history |
| `binary_sensor.example_pet_near_entry` | Door-local proximity, otherwise unknown |
| `sensor.example_pet_alert` | `clear`, `suspected`, `urgent`; acknowledged and affected-door attributes |
| `sensor.example_pet_health` | Radio/transport state plus `storage_ok`, `processing_ok`, `overflow` attributes |
| `sensor.example_pet_light_entry` | Diagnostic `red`, `blue`, `off`, `unknown` intent |
| `input_boolean.example_pet_outputs_enabled` | Enables the generated output bindings |
| `script.example_pet_acknowledge` | Calls `espresense_pet.acknowledge`; never clears the latch |

Use unique IDs and keep these entity IDs unchanged; generated automations target
them explicitly. Room state is available for separate custom room-light bindings.
The integration itself calls no notification or light services.

## Notification scripts and camera evidence

The local `espresense_pet_advisory` event supplies `pet_id`, `level`, `door`, and
`reason`. Generated automations pass those as script variables. An incident may also
include `camera_reference: {camera, event_id}`; missing references are null. The
reference identifies the triggering Frigate evidence. Private notification scripts
can resolve a snapshot/clip using the operator's Frigate endpoint and authentication.
This integration does not construct URLs, fetch media, store credentials or infer
that a generic cat detection identifies the enrolled animal. Heads-up/health/recovery
messages have no incident camera reference. Scripts must tolerate missing or expired
media. Camera/event references stay out of ordinary entity attributes and replay reports.

Events are ephemeral. Enabling outputs does not replay old notifications; inspect the
current alert entity. Enabling does reconcile current known door light intent. Every
external light action rechecks enablement and storage/processing health. Turning off
prevents subsequent generated calls; it cannot cancel a notification script already
started or reset a previously selected preset. Notification scripts that delay or
queue delivery should recheck the enable helper before their own sends.

## Failure and restart behavior

Incident transitions persist in private atomic HA `.storage` before advisory events.
Storage errors leave severity visible but block generated outputs; a successful retry
delivers only the current undelivered severity and reconciles lights. Failed recovery
cannot clear a durable latch. Invalid restored data stops setup instead of silently
starting clear, including corrupt files quarantined by HA. Preserve the damaged
evidence, investigate storage and restore a verified backup before restarting;
deleting incident storage to make setup succeed can erase a real latch. Back up
private HA storage with normal installation backups.

The evidence queue is bounded at 256. Overflow discards queued positive evidence,
resets continuity and marks `overflow: true` until restart. Existing incident latches
remain valid and may still produce red intent; investigate the input rate before
restarting. `processing_ok: false` blocks generated outputs until a corrected restart.
MQTT loss preserves latches, invalidates current proximity and interrupts silence and
recovery timers. Reconnection requires fresh evidence. Neither transport loss nor
unknown proximity changes the last selected light preset automatically.

## Physical acceptance

Verify private contact/node/camera mappings, fit and test the collar, measure
thresholds, and stage a supervised doorway exercise. Test notification and light
delivery explicitly while enabling outputs under supervision. Confirm restart,
disconnect, acknowledgement and recovery behavior on the actual installation.
Verify that camera snapshots/clips reach the intended private recipients. Keep the
physical escape prevention and human supervision in place regardless of software state.

Copy this unchecked checklist to the private setup record and attach actual results:

- [ ] Fit the collar safely and verify the enrolled beacon's observed alias.
- [ ] Verify each node's physical room and every door contact's closed/open states.
- [ ] Measure door-local RSSI thresholds with the actual collar at both sides of each door.
- [ ] Verify camera, threshold and outside zones for the same exterior door; exclude internal doors.
- [ ] With outputs disabled, stage heads-up, Suspected, direct Urgent and stable recovery.
- [ ] Confirm acknowledgement preserves the latch and escalation resets acknowledgement.
- [ ] Confirm broker loss, restart and stale/retained evidence preserve the expected uncertainty/latch.
- [ ] Under supervision, enable outputs and verify intended recipients and available snapshot/clip media.
- [ ] Verify exact WLED off/blue/red presets, brightness/night behavior and unknown-intent behavior.
- [ ] Disable outputs and confirm subsequent actions stop; restart and confirm outputs stay disabled.
- [ ] Record remaining limitations and explicitly approve live activation for the verified mappings.

See
[spec 002](../specs/002-pet-safety/spec.md) and its
[tasks](../specs/002-pet-safety/tasks.md); unchecked work is not implied complete.
