# Plan: Calibration and coverage evidence

## Design

Use separate focused modules under `tooling/calibration` for strict input records,
walk windows/scoring, survey summaries, MQTT normalization/capture, and CLI output.
All scoring is pure over normalized records and explicit schedules; transport has
no placement or calibration mutation path. Unknown topics/payload fields never get
persisted. Use stdlib statistics for medians. Keep normal parsing/scoring offline.

A thin Paho MQTT adapter may be an optional capture dependency; document its pinned
compatible API and test through an injectable client/clock. Bound connection,
duration and shutdown. Record capture completeness/ignored-message counts without
raw identifiers. The normalized log and report use explicit schemas and scoring
versions; the same inputs reproduce the same output. Atomic output writes or
explicit partial-capture metadata prevent a truncated file masquerading as a
completed capture. Stop schedules are validated before capture.

Use public synthetic fixtures with neutral aliases. Store real outputs outside git.
No network devices are written to, and no live calibration is claimed. Initial
entry point is `python -m tooling.calibration`; a fleet CLI alias can forward here
once reconciliation merges, keeping the scorer independent of fleet provisioning.

## Constitution Check

| Principle | Result and planned evidence |
|---|---|
| I. Agent/human operation | PASS: capture/replay CLI plus structured/readable reports. |
| II. Physical world | PASS: stop schedule and walk are human inputs; credentials remain local. |
| III. Configuration as code | PASS: schedules/parameters reproduce scoring, no automatic radio changes. |
| IV. Public/private | PASS: allowlist drops raw identifiers, inputs/outputs external, examples synthetic. |
| V. Evidence | PASS: explicit medians/windows/counts/unknown outcomes backed by boundary tests. |
| VI. Scope | PASS: fleet calibration/coverage diagnostic only. |
| VII. Accuracy | PASS: receiver timing/nearest-node/radio limits explicit; no pet location guarantee. |

## Pre-implementation analysis

All nine requirements map to tasks. Retained status, advertisements' `int`, missing
windows and unequal sample counts cannot substitute for current measurement. No
automatic RSSI adjustment is specified because pinned firmware math and newer
calibration prose can differ. No unresolved constitutional conflicts. Final review
must challenge false-positive success summaries and metadata privacy, not only
happy-path arithmetic.

## Validation evidence

Offline CLI replay and scoring tests pass, including ties, missing windows,
wrong-room plateaus, same-room boundaries, retained observations, incomplete
captures and malformed input without echoing data. Independent five-axis review
found no remaining issues in these modules. All seven constitutional principles
remain satisfied; public fixtures are fictional and outputs remain private.

This PR delivers normalized contracts, scoring, survey summaries and offline CLI.
Live capture and transport tests follow in a separate PR. Physical walk and mounting
acceptance remain deferred under issue #7.
