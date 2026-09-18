# Inspect and reconcile fleet settings

The fleet CLI compares private desired configuration with each node's stored
settings. Only named settings are managed. It preserves unrelated settings and
masked passwords through the existing provisioner's full-form save logic.

Install Python 3.11+ and the repository's `requirements.txt`, then run commands
from the repository root. Copy [the fictional example](../examples/fleet.example.yaml)
to your private repository or ignored local directory. Confirm every address and
room assignment yourself. MAC metadata is descriptive; the CLI does not authenticate
a physical board. Provision new boards through the human-run provisioning path.
Never place Wi-Fi passwords, broker credentials or enrollment keys in inventory.

```powershell
# Read-only inspection. Repeat --node to select several stable IDs.
python -m tooling.fleet diff ../private-config/fleet.yaml
python -m tooling.fleet diff ../private-config/fleet.yaml --node study-node --json

# Preview: GET requests only, exactly as with diff.
python -m tooling.fleet apply ../private-config/fleet.yaml --json

# Deliberately save changed settings and request one restart per changed node.
python -m tooling.fleet apply ../private-config/fleet.yaml --yes --json

# Save and verify stored settings while leaving restart pending.
python -m tooling.fleet apply ../private-config/fleet.yaml --yes --no-restart

# Confirm idempotence after a successful apply.
python -m tooling.fleet diff ../private-config/fleet.yaml --json
```

`diff` performs no writes even if passed `--yes`. Apply requires `--yes` to write;
there is no interactive prompt. Keep reports private: they contain node IDs, room
names and managed values. Output excludes complete live settings, credentials,
HTTP response bodies, inventory paths and raw transport errors. Embedded `irk:`
values are redacted. Do not paste private reports into public issues.

## Inventory contract

The YAML root accepts `site`, `broker`, `defaults` and a nonempty `nodes` list.
Unknown keys and duplicate YAML keys are errors. Each node requires a unique
stable `id` using letters, digits, dots, underscores or hyphens (maximum 64
characters). It may contain `address`, `room`, `settings`, `target`, `mac`, and
`status`. Missing or null addresses mean unprovisioned; missing/null rooms and
metadata are permitted. A provisioned node must have at least one managed setting.

Addresses are hostnames or IPs, optionally with ports, with no URL scheme or path.
Use brackets for IPv6 node addresses, for example `[2001:db8::2]:8080`. Broker hosts
have no port suffix; use `broker.port` separately. IPv6 broker hosts are normalized
to bare IPv6, for example `2001:db8::1`. Duplicate node addresses are rejected after
case, IP, trailing hostname dot and default HTTP port normalization. DNS aliases
that resolve to the same physical device are not detected; list each board once.

`defaults` and node `settings` accept only `main`, `hardware` and `extras`, matching
the existing provisioner. Settings are flat scalar mappings. Use actual YAML
booleans (`false`, `true`), integers for live integer fields, and numbers for live
floating-point fields. Firmware dropdowns can be strings even for numeric options:
on v4.0.6, use `led_1_type: "2"` and `led_1_cntrl: "1"`, but `led_1_pin: 35`
and `led_1_cnt: 1`. Type errors identify the endpoint, key and expected type.
Quoted numeric strings for integer fields, fractional values for integer fields,
nonfinite numbers, nested values, unknown firmware fields and type mismatches fail
closed. Keep YAML `on`/`off` strings quoted if the firmware field is a string.
Credential fields, Wi-Fi SSID configuration and MQTT username changes are rejected;
use the existing human provisioning workflow for these.

Desired values merge in this order: endpoint defaults, root broker, node room,
then node settings. Conflicting root broker/default broker values and conflicting
node room/`settings.main.room` values are rejected. Node broker overrides are
explicit exceptions. An omitted broker port remains unmanaged. Unknown settings
are checked against live fields, so a firmware mismatch fails that node's preflight.
The full inventory is validated before any network request, even with `--node`.

## Results and failure handling

JSON has `schema_version: 1`, `command`, `preview`, `nodes`, `counts`, `error`,
`exit_code` and `scope`. Each node reports its `id`, `status`, managed `changes`,
acknowledged `saved` endpoints, `restart`, `verification` and sanitized `error`.
Changes show the last observed before/desired values; they are not a rollback log.

| Exit | Meaning |
| --- | --- |
| `0` | All eligible selected nodes have verified stored settings convergence. |
| `1` | Read-only inspection/preview found drift and no errors. |
| `2` | Input, request, verification, partial-write or unconfirmed-result error; also no eligible selection. |

Unprovisioned nodes are counted separately as `skipped`; they do not make a
partially provisioned fleet look fully deployed. An all-skipped selection exits 2.
An unavailable or malformed node does not suppress results for independent nodes.

Before writing a node, the CLI reads and validates all its managed endpoints.
It refreshes each changed endpoint immediately before saving, preserves unmanaged
fields, and skips settings that have already converged. These operations are
not atomic: another writer can still race between GET and POST. Use one operator
at a time. Successful saves are acknowledged per endpoint, without blind retries.
A failed save can have reached the node despite a lost response. Inspect the node
before retrying; there is no automatic rollback. A partial save does not trigger
a restart, and any acknowledged saved settings leave restart `pending`.

After all saves succeed, the CLI sends at most one restart request and polls all
managed settings. Restart `acknowledged` means an HTTP acknowledgment, not proof
that a reboot completed. A failed restart response remains `unconfirmed` and exits
2 even when settings readback succeeds. `--no-restart` reports `verification:
stored` with restart `pending`; this may exit 0 because stored state converged.
No-change nodes receive no restart. A subsequent invocation cannot know whether
an earlier operator left a restart pending.

Defaults are a 5-second request socket timeout, a 30-second verification polling
budget, and a 1-second poll interval. Override these with `--timeout`,
`--verify-timeout`, and `--poll-interval` (positive finite seconds, at most 300).
Polling uses the remaining budget for each read. Socket timeouts and the polling
budget are not an absolute process deadline for OS DNS resolution or a server
that continually trickles response bytes. Reads are limited to 1 MiB. Requests
ignore proxy environment variables and never follow redirects.

## Remaining operator acceptance

Automated tests use synthetic stateful loopback HTTP servers; they verify full-form
preservation, checkboxes, refresh behavior, idempotence, independent failures and
failure reporting. They do not prove compatibility with every firmware version.

For the first physical run, confirm node identity/address and wall power, review
the read-only diff, then explicitly authorize your selected nodes with `apply --yes`.
Follow with a clean diff. Independently check fresh MQTT telemetry and online status,
and perform the documented calibration walk. Stored settings convergence does not
prove physical placement, coverage, correct room inference, or completed deployment.
Physical acceptance and real-node writes remain pending for this feature's development.

For a manual single-node path, use
`python tooling/provision/espresense_set.py HOST ENDPOINT` to inspect or supply
explicit `key=value` assignments as described in [the runbook](runbook.md).
That lower-level command writes immediately when assignments are supplied; it does
not provide fleet preview or fleet readback verification.
