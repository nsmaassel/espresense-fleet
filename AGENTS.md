# AGENTS.md — operating and developing espresense-fleet

This is a public toolkit for BLE room presence. A person handles physical actions
and enters secrets locally; the agent operates the tooling, records evidence, and
keeps deployment details outside this repository.

## Route the work first

- **Set up or troubleshoot a fleet:** read [`docs/runbook.md`](docs/runbook.md),
  then the relevant layout, fleet, calibration, or pet-safety guide. Follow each
  guide's observable done checks. The runbook owns board-specific facts and the
  end-to-end setup sequence.
- **Maintain an existing capability:** find its owning directory under `specs/`
  and read that feature's `spec.md`, `plan.md`, and `tasks.md` before changing its
  behavior. Update those artifacts when requirements, design, status, or remaining
  work changes. A correction that does not change intended behavior can stay local
  to the affected code or documentation.
- **Add a distinct capability or stage:** follow [`docs/development.md`](docs/development.md)
  to run the installed Spec Kit flow and create a new numbered feature.
- **Change project-wide principles:** use `speckit-constitution` as a separate,
  reviewed governance change. Feature work consumes the constitution; it does not
  recreate or casually amend it.

When no feature is selected, do not guess one from an old branch or local selector.
Identify the owning feature from the requested behavior and current files, or create
a new feature when the work is independently deliverable.

## Public/private boundary

Use fictional public fixtures. Keep real MACs, IPs, SSIDs, room geometry, floor
plans, broker details, captures, and generated reports in an operator's private
repository or ignored local directory. Passwords and `irk:` enrollment keys stay
outside every git repository and out of chat; prompt for them only in the person's
local terminal. Treat an IRK as a tracking credential.

Provisioned nodes run from ordinary power. A host USB serial driver can leave an
ESP32-S3 in download mode, and opening its serial port can reset it. Use USB for
flashing and provisioning, then verify a deployed node over the LAN and MQTT.

## Development completion

Review applicable constitutional constraints before implementation and delivery.
Run `python tooling/governance/check_repository.py`, applicable tests, and an
in-agent code review. Report automated evidence separately from hardware or
household validation. Passing scripts proves structure and known-pattern checks;
it does not prove privacy, radio accuracy, or physical acceptance.

Ask before creating a public repository, issue, pull request, or other externally
visible artifact unless the current session already authorizes publication.
