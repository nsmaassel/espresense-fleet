# Pet-safety tasks

- [x] T001 Strict private configuration and fictional examples (FR-001).
- [x] T002 Pure freshness, room hold, history, proximity and health state (FR-002, FR-003, FR-004, FR-009).
- [x] T003 Per-door ladder, monitored silence, recovery, acknowledgement and persistence contract (FR-005, FR-006, FR-007, FR-008).
- [x] T004 Strict ESPresense/Frigate ingress and deterministic replay CLI (FR-002, FR-005, FR-013).
- [x] T005 HA lifecycle, ordered processing, private storage, services and entities (FR-008, FR-009, FR-010, FR-012).
- [x] T006 External package generator and disabled configurable outputs (FR-001, FR-011, FR-013).
- [x] T007 Boundary, replay, real HA schema/lifecycle tests and independent review (FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013).
- [x] T008 Operator documentation and private activation checklist (FR-014).
- [ ] T009 Human physical validation and explicit live activation (FR-014).

Software tasks are implemented and independently reviewed. All 131 ordinary tests and
17 actual HA 2026.9.2 runtime tests passed independently. The operator guide includes
a copyable unchecked private acceptance checklist. MQTT transport and output services
are stubbed in runtime tests; physical acceptance remains a separate operator task.
