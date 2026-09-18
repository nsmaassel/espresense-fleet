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

Configuration and ingress validation pass their targeted synthetic tests and independent
review. This first delivery establishes inputs and the complete feature plan. Domain
engine/replay and HA runtime/package delivery remain separate work. A local WSL
Python 3.14.2 / HA 2026.9.2 runtime initializes successfully in disposable storage;
that is test-harness evidence, not validation of the unfinished integration.
