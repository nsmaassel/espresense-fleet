# Fleet foundation implementation plan

Recovered from the approved September 17 setup session. The user selected a public
`espresense-fleet` repository, reusable onboarding/tools, an offline layout editor,
and private House 1 configuration in homelab. This delivery completes US1/US2 tooling;
US3–US6 remain future work rather than implied live features.

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
