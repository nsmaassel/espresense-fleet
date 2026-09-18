# Fleet foundation implementation plan

Recovered from the approved September 17 setup session. The user selected a public
`espresense-fleet` repository, reusable onboarding/tools, an offline layout editor,
and household configuration in a separate private repository. This delivery completes US1/US2 tooling;
US3 is delivered separately by [spec 004](../004-fleet-reconcile/plan.md).
US4–US6 remain future work rather than implied live features.

## Constitution Check

Reviewed against constitution 1.0.1 during the Spec Kit adoption. This records the
current design review, not a claim that the original scaffold ran the CLI gates.

| Principle | Design and evidence | Status |
|---|---|---|
| I. Agent and human operation | Commands and runbook completion checks; FR-001, FR-005. | Software covered; hardware acceptance pending. |
| II. Human physical steps | Operator plugs in boards and enters secrets locally; FR-004. | Preserved. |
| III. Configuration as code | Pinned firmware; geometry is the layout source; FR-002, FR-006. | Foundation covered; fleet reconciliation is deferred US3. |
| IV. Public/private separation | Fictional examples and external config paths; FR-003. | Reviewed; deployment records stay private. |
| V. Recorded evidence | Offline and browser tests below; physical calibration needs site records. | Software verified; site validation pending. |
| VI. Scope | US1/US2 deliver flashing, provisioning and layout only. | In scope; future stories remain unchecked. |
| VII. Accuracy honesty | No universal BLE accuracy guarantee; measure after mounting. | Preserved. |

Recheck these entries after design changes and before implementation review. A
passing structural check does not establish semantic compliance with the constitution.

## Boundaries

- `tooling/flash`: locked firmware downloads and esptool invocation; no credentials.
- `tooling/provision`: the ESPresense HTTP form contract and Windows Wi-Fi handoff.
  Preserve existing fields and masked secrets; omit false checkboxes.
- `tooling/layout`: validated geometry, coordinate transforms, Companion serialization,
  and offline editor generation. Edited geometry is downloadable to avoid copying
  house-frame coordinates back into local-frame fields by mistake.
- `examples`: fictional inputs. Private plans, inventory and site settings live outside
  this repository. Device labels stay stable when room assignments change.

No live firmware update, renaming, Wi-Fi change, broker restart, or Companion deployment
is needed to validate this software delivery. Mounting and calibration require the owner.

## Evidence

Offline tests cover form preservation, false checkbox overrides, checksum refusal,
floor transforms, and coordinate/export round trips. Browser tests exercise editor
changes and export. Firmware downloads and Companion schema are checked against
upstream. Hardware flashing remains an explicit acceptance step; mocked tests do not
prove a successful flash or usable Wi-Fi coverage.

## Follow-on deployment

1. Label the remaining boards and bind each physical ID to its planned room.
2. Flash/provision one at a time; verify fresh status/telemetry, then mount.
3. Establish sufficient usable node coverage on both floors, run Companion, and
   measure room transitions with the enrolled phone.
4. Calibrate the collar beacon when available. Specify door/contact/camera fusion
   separately before building or enabling pet alerts.
