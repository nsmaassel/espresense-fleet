# espresense-fleet

Reproducible setup for [ESPresense](https://espresense.com) Bluetooth presence nodes:
flash firmware, provision Wi-Fi and MQTT, and place nodes on a floor plan for
[ESPresense Companion](https://espresense.com/companion).

**Pre-alpha.** This first release provides reusable AtomS3 Lite setup tools.
Fleet size and placement depend on the installation. Full-house coverage and pet
alerts are not validated. BLE distances are estimates, and room accuracy needs testing in each home.

Development follows [the constitution and Spec Kit workflow](docs/development.md).

## Start here

With a coding agent, open this repository and describe your boards, MQTT broker,
and floor-plan images. The agent follows [AGENTS.md](AGENTS.md); you connect boards,
enter credentials locally, pair your phone, and walk the calibration route.

By hand:

1. Create a Python 3.11+ virtual environment and run `python -m pip install -r requirements.txt`.
2. Read the [setup runbook](docs/runbook.md). Confirm your broker is reachable from the node Wi-Fi.
3. Flash a connected AtomS3 Lite:
   `python tooling/flash/flash_node.py --port COM6 --watch`
   (use `/dev/ttyACM0` on Linux).
4. Provision from Windows PowerShell:
   `pwsh -File tooling/provision/Setup-ESPresenseNode.ps1 -ApSsid espresense-xxxxxx -RoomName kitchen -HomeSsid MyWifi -MqttHost 192.0.2.20`
5. Configure the board LED and verify a fresh MQTT report using the runbook.
6. Follow the [layout guide](docs/layout.md) to build an offline editor and export Companion YAML.
7. Use the [fleet guide](docs/fleet.md) to inspect managed settings against your private inventory before explicitly applying changes.
8. Follow the [calibration guide](docs/calibration.md) to record a timed walk and replay room and radio diagnostics.

The example broker `192.0.2.20` is a documentation-only address; replace it with your broker.

## Available and planned

| Capability | Status |
| --- | --- |
| Flash four firmware partitions with SHA-256 verification | Available; AtomS3 Lite target |
| First-time Wi-Fi/MQTT provisioning | Windows script; manual Wi-Fi join on Linux/macOS |
| Read/change settings over the LAN | Available; preserves masked stored passwords |
| Offline floor-plan editor and Companion export | Available; geometry is supplied by an operator or agent |
| Phone enrollment | Documented manual procedure |
| Fleet settings diff/apply | Available with preview by default and stored-settings readback; [fleet guide](docs/fleet.md) |
| Walk capture, scoring and coverage survey | Available with explicit missing-data and capture-completeness reporting; [calibration guide](docs/calibration.md) |
| Pet advisory model and offline replay | Available for synthetic scenarios; [guide](docs/pet-safety.md) |
| Home Assistant pet advisory integration/package | Available with outputs disabled by default; [installation and acceptance guide](docs/pet-safety.md); physical acceptance required |

## Keep your home private

This public repository contains software and fictional examples. Keep real node
addresses, Wi-Fi names, floor plans, and inventory in a private repository or in
ignored `private/`. Enrollment IRKs and passwords are credentials: keep them out
of git, including private git repositories. Generated editor pages embed floor
plans and coordinates; treat them as private too. The editor runs offline.

## Development

Run `python -m unittest discover -s tests -v` after installing requirements.
HA runtime tests use Linux Python 3.14.2 and `requirements-ha-test.txt`:
`python -m unittest discover -s tests_ha -v`. They stub MQTT and external actions;
no household broker, light or notification channel is contacted.
See [the implementation plan](specs/001-fleet-foundation/plan.md) for scope and
[the task list](specs/001-fleet-foundation/tasks.md) for hardware checks still needed.

Firmware pins live in `tooling/flash/firmware.lock`; update them through review.
Examples use invented homes and documentation-only addresses. MIT licensed.
