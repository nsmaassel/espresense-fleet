# Spec 004: Fleet settings reconciliation

**Status:** Implemented and independently reviewed; physical write/placement acceptance remains deferred.
**Tracks:** Issue #5; foundation US3.

## User story

An operator supplies their private inventory, sees which managed settings differ on
each configured node, and explicitly applies those differences without replacing
unrelated settings or handling new credentials. An agent can inspect structured
results and tell saved configuration from an unreachable or partially changed node.

## Requirements

- **FR-001**: Read external YAML inventory with stable node IDs, host/IP addresses, room names, optional broker host/port, optional endpoint settings defaults, and per-node endpoint overrides. Validate the complete inventory before network access; reject duplicate IDs/addresses, unknown schema keys, invalid ports/addresses, nested setting values, nonfinite numbers, and desired credentials. Missing/null addresses are unprovisioned nodes, reported as skipped.
- **FR-002**: Expose `python -m tooling.fleet diff INVENTORY` and `apply INVENTORY`. Support an explicit node selection, human table output, and `--json`. Diff and apply without `--yes` perform reads only; apply without `--yes` clearly reports a preview. Only explicitly managed settings contribute to drift.
- **FR-003**: Reuse the provisioner's effective settings merge, full-form construction, false-checkbox omission and masked-secret preservation. Validate desired scalar types against live field types, including integer-versus-fraction rejection and finite numbers, before any write for that node. Unknown endpoint fields fail closed.
- **FR-004**: Apply rereads each changed endpoint before a single save, preserves unmanaged fields and credentials, skips already converged values, and performs at most one restart per changed node after successful saves. Never blindly retry a write or claim atomic rollback.
- **FR-005**: Read back managed settings and verify convergence after restart using bounded polling. With `--no-restart`, verify stored settings but explicitly report that restart/operational validation remains pending. Failed, partial or unconfirmed writes cannot be reported as success; a successful restart request alone is insufficient.
- **FR-006**: Continue reporting independent nodes when one is unavailable or malformed. Exit 0 for verified convergence, 1 for drift in a read-only inspection, and 2 for input, network, verification or partial-write errors. An empty eligible selection is an error, not a successful deployment. Skipped unprovisioned nodes are counted separately.
- **FR-007**: Output only managed changes and sanitized status/errors; never dump HTTP bodies, complete live settings, secrets or raw exception messages. Inventory validation errors do not echo rejected secret values. Public fixtures use fictional nodes; local reports remain private and cannot be assumed safe to publish.
- **FR-008**: Provide deterministic tests through real local HTTP endpoints for no-write diff/preview, full-form save, false checkbox, preserved credentials, readback failure, idempotence, multiple endpoints, partial failure and independent-node reporting. Document exact operator commands and the remaining physical acceptance steps.

## Input contract

Inventory fields: optional `site`, optional `broker: {host, port}`, optional
`defaults: {main: {...}, hardware: {...}, extras: {...}}`, and required `nodes`.
Each node contains required `id`, optional `address`, optional `room`, optional
`settings` with the same endpoints, and optional metadata `target`, `mac`, `status`.
MAC metadata is not a verified identity assertion; addresses must come from the
operator's confirmed inventory. Do not infer physical room assignments.

Effective desired settings use defaults, then root broker fields in `main`, then
node room in `main`, then node endpoint settings. Reject conflicting node room versus
`settings.main.room`, and conflicting root broker versus `defaults.main.mqtt_host`
or `mqtt_port`; overrides in node settings are explicit site exceptions. Configuration
files never carry Wi-Fi, MQTT or enrollment credentials. Initial credentials use
the existing human-run provisioning path. HTTP writes are limited to the existing
supported endpoint set; no arbitrary URLs or redirect destinations.

## Acceptance and limits

The same successful apply followed by diff reports no drift. Changing a desired
false checkbox does not enable it, and a saved field is verified rather than merely
acknowledged. An unreachable node cannot hide another node's drift or failure.
The command records stored settings convergence, not MQTT telemetry, identity,
physical coverage, room accuracy, or a completed deployment. No live writes are
part of this development stage. Firmware and physical setup are unchanged.
