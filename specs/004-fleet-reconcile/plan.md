# Plan: Fleet settings reconciliation

## Design

Add a small `tooling.fleet` module entry point with separated inventory validation,
HTTP orchestration/reconciliation, and CLI reporting. Reuse the existing provisioner
for effective settings and full-form construction rather than duplicating the API
contract. Keep each authored module focused and roughly below 300 lines.

Validate the entire inventory first (FR-001). Resolve the selected stable IDs and
managed endpoint settings before touching HTTP. Use bounded GET/POST requests to
operator-supplied hosts, reject redirects, and preflight every desired endpoint for
a node before its first save (FR-003). Inspect all nodes independently. Re-read a
changed endpoint immediately before building the full form, and skip a write if
it has already converged (FR-004). Writes remain per-endpoint and non-atomic.

Separate inspection, saving, restart and verification statuses. Read back actual
values, normalize types without lossy numeric conversion, and keep partial/unknown
outcomes as failures (FR-005, FR-006). CLI has stable JSON plus a compact human table;
errors reveal their category rather than raw remote data (FR-002, FR-007).

Python 3.11+, stdlib HTTP and existing PyYAML dependency suffice. Tests run only
against in-process loopback HTTP servers and synthetic inventories. Fixtures make
saved state observable, count writes/restarts, and intentionally reject or ignore
requests to exercise failure semantics (FR-008).

## Constitution Check

| Principle | Result and evidence planned |
|---|---|
| I. Agent/human operation | PASS: CLI, JSON exits and manual runbook provide both paths. |
| II. Physical steps | PASS: no flashing, pairing, placement or credential entry automated here. |
| III. Configuration as code | PASS: desired inventory drives diff/apply with readback; unmanaged values preserved. |
| IV. Public/private | PASS: external inventory, fictional fixtures, reject desired secrets, sanitized reports. |
| V. Evidence | PASS: stateful HTTP tests prove settings behavior; live acceptance separately pending. |
| VI. Scope | PASS: foundation US3, fleet reconciliation only. |
| VII. Accuracy | PASS: settings convergence is distinct from MQTT/coverage/room accuracy. |

## Pre-implementation analysis

All eight requirements map to tasks. Known pitfalls addressed: integer truncation
in the lower-level provisioner is blocked by fleet validation; stale whole-form
writes get a fresh read; partial saves cannot imply rollback; masked credentials
stay confined to the same device request. Reports may contain private managed
values and are documented as private despite credential redaction. No unresolved
constitutional conflicts. Recheck after implementation and record actual evidence.

## Validation evidence

- Python 3.11 on Windows: 57 tests passed, including 23 fleet-specific tests. Compilation and governance checks passed; publishable files scanned clean with Gitleaks.
- Actual subprocess CLI tests use stateful loopback HTTP, including full-form preservation, typed dropdown fields, false checkboxes, drift preview, independent failures, idempotence, refreshed state, partial saves and failed readback/restart responses.
- A read-only v4.0.6 check confirmed expected fields and exposed string-valued LED dropdowns; examples and tests now reflect those types. No real-device writes were performed.
- Independent round-one review found malformed Unicode could escape the transport boundary and stop the entire fleet. Regression tests reproduce it; UTF-8 preflight and guarded form encoding now isolate the failure. Delta review independently reran the reproduction and approved the fix with no new findings.
- All seven constitutional checks remain satisfied. Restart acknowledgment means an HTTP response, not proof of a completed reboot. Hardware write, fresh MQTT and placement acceptance remain pending in issue #7.
