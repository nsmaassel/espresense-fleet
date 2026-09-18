# Plan: Pet advisories with one state machine

## Architecture

One HA custom integration (`custom_components/espresense_pet`) owns validated
configuration, a pure injected-time engine, strict MQTT ingress, serialized runtime
coordination/persistence and proper HA entities. The generator under `tooling/pet`
creates the private HA package with outputs initially disabled. It does not duplicate
state logic in YAML. Ordinary Python tests import the pure modules without HA;
optional real-HA tests run on Linux Python 3.14.2 with HA pinned to 2026.9.2.

Module ownership/seams:
- `config.py`, `engine.py` and focused engine helpers: validated domain and state.
- `ingress.py`: pinned ESPresense and Frigate payloads to domain events.
- `__init__.py`, `coordinator.py`, sensor platforms: HA lifecycle, ordered dispatch,
  MQTT health, private Store persistence, services and entity publication.
- `tooling/pet`: external config validation, package generation and offline replay.
- Tests use the same domain engine; HA tests exercise actual classes/services/schema.

Keep files under 300–400 lines, separating presence from incident policy if needed.
No production deploy, MQTT publication, camera edits or notification sends occur.
Feature PRs are split into domain/replay, adapter and package/runtime validation as
needed; unchecked tasks continue to describe the full intended delivery.

## Constitution Check

| Principle | Result and evidence plan |
|---|---|
| I. Agent/human operation | PASS: generated package, replay CLI and manual installation/acceptance guide. |
| II. Human physical steps | PASS: hardware, mapping verification and live activation stay with operator. |
| III. Configuration as code | PASS: explicit private maps, bounded parameters and reviewable generated YAML. |
| IV. Public/private | PASS: fictional fixtures; external config/report/package paths; credentials remain HA-managed. |
| V. Evidence | PASS: deterministic boundary tests plus real HA lifecycle/schema tests and private physical checklist. |
| VI. Scope | PASS: the already-planned ESPresense pet-safety layer only. |
| VII. Accuracy | PASS: recent observations are evidence, not containment; camera class is not pet identity. |

## Decisions before implementation

The active goal authorizes local implementation. Existing private planning establishes
the ladder, latching and configurable home setup. Remaining deployment decisions are
external mappings, never hardcoded assumptions. Acknowledgement is explicitly separate
from recovery, avoiding the older ambiguity that a button press proves return.
Outage time never counts as monitored silence or stable recovery. Restored incidents
remain latched and visible. A fresh full monitoring interval after restart is deliberate.
Pure YAML was rejected because HA MQTT automation triggers omit the retain flag and
helper/timer semantics would duplicate fragile state transitions.

## Analysis before implementation

FR-001–FR-014 map to tasks. No constitutional conflicts. Primary risks are stale evidence,
transport gaps, replayed camera events, ordered storage and action delivery. Tests must
exercise those paths against the actual engine/HA adapter. No safety claim is supported
by green tests alone. Notification delivery and real collar performance remain unchecked.

## Validation

Configuration, ingress and domain/replay validation passed their targeted synthetic
tests and independent review. Adapter/package tests use an isolated local Linux
Python 3.14.2 / HA 2026.9.2 environment with disposable storage. MQTT I/O and external
output services are stubbed; HA package merging, startup, storage, entities, services,
scripts and automations are real. CI pins the same runtime.


### Domain/replay delivery evidence

Independent five-axis review found a P2 room-debounce bypass: retained room history
could become current room after one report following a gap/reconnect. The fix separates
current qualification from retained history. Four regressions reproduced the original
failures and now pass; the reviewer independently verified all 47 pet tests with no
remaining required findings. CLI replay includes latch, acknowledgement, restart,
missing freshness and eventual stable recovery. Input filtering uses the same camera-ID
contract as the engine. These prove software behavior only; HA adapter/package/runtime
and physical acceptance remained outstanding at that checkpoint. Principles I–VII
remain satisfied.

### Adapter/package review decisions

Generated outputs recheck enablement before each action, including after an awaited
light turn-on. This closes an independently reproduced race where disabling outputs
could leave a later preset call running. Output bindings also require healthy storage
and processing. The adapter publishes health before light entities so a failed save
cannot race a state-triggered output. Recovery of storage reconciles current light
intent; notification retry coalesces to the current severity. Private notification
scripts receive bounded camera/event references for snapshot/clip resolution, without
public credentials, network locations or media. No media fetching occurs here.

Corrupt incident storage must be distinguished from a genuine first run, including
HA-quarantined files on later restarts. Queue delay must never make expired evidence
current or permit recovery. These are explicit boundary cases in the pinned-runtime
suite, alongside orderly shutdown, retained data, overflow and failed persistence.

Final independent review approved all five axes with no required findings remaining.
The reviewer independently ran all 131 ordinary tests and 17 actual HA runtime tests,
plus repository governance and whitespace checks. The reviewed fixes cover corrupt
JSON and a subsequent quarantine-only restart, action guards during disable/save
failure, and queue-delayed observations/camera frames. Principles I–VII pass the final
review: software is reusable and configurable, public fixtures remain fictional,
and physical measurements, output delivery and activation remain explicitly unchecked.
