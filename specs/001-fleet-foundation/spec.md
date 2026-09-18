# Spec 001 — Fleet foundation

**Status:** US1/US2 software merged; US3 implemented in spec 004; hardware acceptance pending · **Created:** 2026-09-17
**Target:** M5Stack AtomS3 Lite fleets, with operator-supplied inventory and geometry.

## Problem

Setting up ESPresense today is a series of one-off manual steps: a browser flasher, a captive
portal per node, hand-drawn room polygons in YAML, and calibration by staring at numbers. It
does not scale past two or three nodes, it is not reproducible, and it cannot be handed to
someone else — or to an agent. Operators need to reproduce a fleet at another site and
hand the same workflow to someone using a coding agent.

## Users

- **Operator with an agent** — points Claude Code/Cursor/Copilot at the repo; does the physical steps.
- **Operator by hand** — follows the runbook; same tooling, no agent.
- **Household** — never touches any of this; sees a room on a dashboard and a light by the door.

## User stories

### US1 — First node in under ten minutes (P1)
As an operator, I plug in a board and run one flash command and one provision command, and the
node reports `online` on my broker.
**Acceptance:** `flash_node.py` verifies checksums and writes all four images; the provision
script joins the setup AP, saves settings, restarts, rejoins home Wi-Fi; `espresense/rooms/<room>/status`
= `online` within 60 s. The Wi-Fi password is entered only in the operator's terminal.

### US2 — Floor plan from plan images (P1)
As an operator, I hand over dimensioned plan images (magicplan export or similar) and get back
Companion `floors:` with room polygons in metres, plus an editor to place nodes on real outlets.
**Acceptance:** geometry lives in one source file; the editor is a single offline HTML file
built from it; dragging a dot updates house coordinates; "Copy YAML" round-trips exactly into
the geometry source; per-floor flip/offset controls exist because plans are not aligned.

### US3 — Fleet reconcile (P2)
As an operator, I run `fleet diff` and see every node whose live settings differ from
`nodes.yaml` (room, MQTT, LED, timeouts); `fleet apply` reconciles without a password.
**Acceptance:** uses `GET/POST /wifi/<endpoint>` with the masked-password round-trip;
never sends a checkbox key for `false`; prints a table; exit code non-zero on drift.

### US4 — Calibration as a procedure (P2)
As an operator, I run `fleet calibrate --device <id> --stops "kitchen,office,kitchen"`, walk,
and get a report: per-window winner, clean flips vs false flips, per-node minimum distance,
and a recommendation (move node / adjust `rx_adj_rssi` bounds).
**Acceptance:** report reproducible from a saved log; flags a node that never hears the device
below 3 m; output suitable for pasting into an issue.

### US5 — Coverage survey (P3)
As an operator, before mounting I get a table of Wi-Fi RSSI per node position and node-to-node
BLE distance, with warnings for < −70 dBm Wi-Fi and nodes within 2 m of a router.

### US6 — Pet-safety package (P2, separate spec 002)
Door-zone node + door contact + camera event → latched, tiered alert with cool-downs; status
lights per door. Parameterized by beacon id, doors, nodes, camera zones, notify targets.

## Requirements

- **FR-001**: Tooling is Python 3.11+ (esptool, stdlib) plus one PowerShell script for the Windows
  Wi-Fi join; a shell equivalent for Linux/macOS is a follow-up.
- **FR-002**: Firmware is pinned in `tooling/flash/firmware.lock` (URL + sha256 for app, bootloader,
  partitions, boot_app0) per target; bumping is a PR.
- **FR-003**: Private configuration is supplied by external paths and arguments; public examples are fictional.
- **FR-004**: All node settings writes go through the documented HTTP API; no serial after provisioning.
- **FR-005**: Every operational command documents its effect and a completion check an agent can parse.
- **FR-006**: Offline layout editing preserves geometry and metadata on export and emits Companion floors and nodes.

## Non-goals

Replacing ESPresense Companion's locator; generic HA dashboards; supporting boards we have not flashed.

## Open questions

- Linux/macOS Wi-Fi join for the provisioning step (nmcli / networksetup) — needed before others can use US1 outside Windows.
- US3 uses `python -m tooling.fleet diff|apply`; see [spec 004](../004-fleet-reconcile/spec.md).
- Companion export now includes both `floors:` and `nodes:` from the geometry source (US2).

## Log

- 2026-09-17 — Drafted from an operator-assisted setup. Deployment observations stay in the operator's private records.

- 2026-09-18 — Resumed interrupted scaffold. Constitution 1.0.1 corrects the unsupported universal room/map accuracy claim; site calibration remains mandatory. US1/US2 software is the initial delivery, with hardware acceptance explicitly pending.
