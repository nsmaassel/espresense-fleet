# Foundation tasks

Requirement IDs refer to this feature's spec. Completed items describe the software
in the merged foundation/layout PRs, not a finished physical deployment.

## Software recovery (this delivery)

- [x] T001 [FR-003] Recover and review the scaffold without household data in public files.
- [x] T002 [FR-001, FR-002, FR-004] Validate firmware checksums and preserve existing HTTP settings.
- [x] T003 [FR-006] Provide offline geometry editing and Companion export with round-trip tests.
- [x] T004 [FR-001, FR-003, FR-005] Add fictional examples, installation steps, runbook completion checks and CI.
- [x] T005 [FR-003] Keep accepted deployment geometry and inventory in the operator's private repository.

## Hardware acceptance (requires physical setup)

- [ ] T006 [FR-001, FR-002, FR-004, FR-005] Run the recovered flash and provisioning tools on an unprovisioned board.
- [ ] T007 [FR-003] Label remaining boards and confirm each room assignment in private inventory.
- [ ] T008 [FR-005] Verify Wi-Fi/MQTT at each outlet before mounting; retain results privately.
- [ ] T009 [FR-003, FR-006] Confirm floor alignment and room names; mark doors and router positions privately.
- [ ] T010 [FR-003, FR-006] Deploy Companion and record a private calibration walk.

## Later stories

These require expanded requirements and a reviewed plan before implementation.

- [x] T011 US3: fleet diff/apply with explicit desired config; implemented and validated under [spec 004](../004-fleet-reconcile/tasks.md).
- [x] T012 US4: record and score calibration walks; software delivered under [spec 005](../005-calibration-evidence/tasks.md), physical walk remains pending.
- [x] T013 US5: coverage survey diagnostics; software delivered under [spec 005](../005-calibration-evidence/tasks.md), physical placement remains pending.
- [x] T014 US6: pet advisory integration and Home Assistant package delivered under [spec 002](../002-pet-safety/tasks.md); physical validation and activation remain pending.

Physical acceptance is tracked in [issue #7](https://github.com/nsmaassel/espresense-fleet/issues/7); private deployment records stay outside this repository.
