# espresense-fleet Constitution

**Version 1.0.1 · Ratified 2026-09-17 · Accuracy wording corrected 2026-09-18**

## Purpose

Make a fleet of ESPresense nodes as reproducible, inspectable and boring to operate as any
other piece of home infrastructure — and make the first setup something a coding agent can
do for a person who has never flashed a board.

## Principles

### I. Agent-operable first, human-operable always
Every stage has a command an agent can run and a "done" check it can verify without a human
reading a screen. Every stage also has a documented manual path. If a step can only be done by
clicking in a GUI, it is not finished.

### II. The physical world stays with the human
Plugging in boards, moving them to outlets, walking the calibration route, pairing a phone,
and typing a Wi-Fi password are the human's. Tooling prompts for secrets in the human's own
terminal and never receives them from an agent or a chat transcript.

### III. Configuration is code; the fleet converges to it
`nodes.yaml` and the Companion config are the source of truth. Firmware is pinned with
checksums. Tooling reads a node's live state, diffs it against git, and reconciles — it does
not treat the device as the record. Manual changes on a node are drift.

### IV. Public tooling, private homes
This repository never contains a real house: no MACs, IPs, SSIDs, floor-plan coordinates or
enrollment keys. Tooling accepts paths and arguments; examples are fictional. An IRK is
treated as a credential. Violations are fixed by rewriting history, not by a follow-up commit.

### V. Evidence over vibes
Placement, calibration and "it works" are backed by recorded data: Wi-Fi RSSI per spot,
node-to-node distances, walk logs scored for clean vs false room flips. A change to node
placement or optimizer bounds cites the report that motivated it.

### VI. Scope: ESPresense fleets and the pet-safety layer
In scope: flashing, provisioning, layout, calibration, reconciliation of ESPresense nodes;
ESPresense Companion configuration; a Home Assistant package that fuses room presence with
door contacts and camera events into tiered, latched alerts and status lights. Out of scope:
generic home automation, dashboards beyond the presence map, other presence technologies
(unless they publish into the same room model).

### VII. Honest about accuracy
Docs distinguish measured results from expectations. BLE room and coordinate estimates
depend on geometry, radio conditions, body occlusion, and calibration. This project has
not established a universal accuracy bound. Nothing promises to find a cat under a specific bed.

## Governance

- Changes to principles require a version bump here and a note in the spec that motivated it.
- Specs live in `specs/NNN-name/`; a stage that does not exist yet gets a spec before code.
- Reviews check: does it run unattended by an agent? does it leak a home? is the claim measured?
