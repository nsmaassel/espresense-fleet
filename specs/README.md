# Feature artifacts

These directories record contributor intent and evidence. They are not the setup
manual; operators start with [`docs/runbook.md`](../docs/runbook.md).

| Feature | Owns | Current state |
| --- | --- | --- |
| `001-fleet-foundation` | flashing, first provisioning, layout foundation, original roadmap | software merged; remaining hardware acceptance is explicit in its tasks |
| `002-pet-safety` | advisory model and Home Assistant integration | software merged; deployment and physical acceptance remain external |
| `003-spec-kit-governance` | project instructions, Spec Kit assets, governance checks | implemented and maintained in place |
| `004-fleet-reconcile` | private inventory diff and explicit settings apply | software merged; physical write/placement acceptance remains external |
| `005-calibration-evidence` | bounded capture, scoring, and coverage evidence | software merged; physical acceptance remains external |

Maintain an existing feature when a change adjusts behavior already owned by its
requirements. Add a numbered feature when the work introduces an independently
deliverable capability or a material scope boundary. The project constitution is a
shared constraint consumed by feature planning and implementation; it is amended
only when the governing principles themselves change.

See [`docs/development.md`](../docs/development.md) for selection, the pinned Spec Kit
flow, and validation commands.
