# Spec 002: Configurable pet presence and escape advisories

**Status:** Software implementation authorized by the operator's instruction to continue locally; deployment and physical acceptance remain deferred.
**Created:** 2026-09-18 · **Scope:** Foundation US6 · **Tracks:** issue #11.
Recovered behavior is generalized from private planning; household mappings stay private.

## User scenarios and acceptance

1. As an operator, I want stable room and per-door proximity evidence with explicit freshness. Continuing observations accept a new room; a single report followed by silence cannot pass the hold or clear an incident. Silence never proves the animal is outside.
2. As a household member, I want tiered door/camera advisories. Opening while near produces a heads-up; a cat camera observation after an opening can latch Suspected or Urgent. Correlation stays within one exterior door; internal doors only provide proximity.
3. As an operator, I want latches to survive restart and acknowledgement. Only continuing fresh indoor observations clear and re-arm; outages preserve the latch and disclose unavailable evidence.
4. As an operator with or without an agent, I want a reusable HA package and integration. Configuration adapts it to my home. Outputs start disabled. Synthetic runtime tests establish behavior; a real collar/door/camera exercise remains separate.

## Requirements

- **FR-001**: Strictly validate versioned configuration for one subject per HA instance: neutral ID/display name, friendly enrolled device alias, explicit node-to-room/MQTT-slug maps, door contact entities, node sets, exterior flags and camera/zone maps. Reject unknown keys, duplicate IDs, raw credential selectors, nonfinite/boolean numeric values and invalid selectors. Bound collections/timings. Public examples are fictional.
- **FR-002**: Use receipt-relative monotonic time for live evidence. Discard retained, malformed and unmapped MQTT reports before state changes. Valid identical reports refresh evidence. Only finite distance/RSSI reports from mapped indoor nodes count; retained status and HA state-change timestamps are not receipt evidence.
- **FR-003**: The nearest fresh nodes yield a diagnostic room candidate when all minimum-distance nodes map to one room; ties across different rooms are unknown. Accept after 30 seconds of continuing candidate with no gap over 20 seconds. Retain the last accepted room for ten minutes after its last qualifying observation. Expose separate fifteen-minute recent-indoor history, never proof of containment. Intervals are configurable.
- **FR-004**: Per-door proximity requires a configured door node at or above its calibrated RSSI threshold (default -65dBm) within the freshness interval. A real exterior-door closed-to-open contact transition while near emits at most one heads-up per cooldown (default 60s). Unknown/unavailable/restored-open contacts do not manufacture an opening.
- **FR-005**: Correlate cat camera observations with a preceding opening of the same exterior door within 180s by observation time. Inside threshold latches Suspected; outside zone latches Urgent and may skip Suspected. Reject stale/future frames, ended/false-positive events, unknown cameras/zones and repeated zone evidence. A cat class does not identify the enrolled animal. Historical entered_zones is not current occupancy.
- **FR-006**: While Suspected, 180s without credible fresh indoor evidence escalates to Urgent only during continuously available MQTT monitoring. Transport loss interrupts the silence interval; reconnection starts a full monitored interval. Existing severity/latch remains visible. Silence without a correlated incident never creates an escape incident.
- **FR-007**: Severity only increases until 60s of continuing fresh stable indoor-room evidence received after the incident clears it. Gaps, room contradiction or transport loss reset recovery. Manual acknowledgement is separately persisted and never clears/re-arms. Repeated camera evidence from the same event/door/stage must not reopen after recovery within the bounded 256-entry deduplication history. Old frame timestamps also fail freshness; finite history is not an indefinite replay guarantee.
- **FR-008**: Persist severity, affected doors, highest-severity origin door, acknowledgement and bounded consumed-camera-event history in private atomic HA storage. Restore no radio freshness, proximity, candidates or recovery timers. Validate stored data. Storage failure visibly degrades durability and cannot silently clear state. Restart cannot clear/downgrade; a full monitored silence interval after restart deliberately excludes unobserved offline time.
- **FR-009**: Expose collar/transport health separately. Thirty minutes without target observations during continuous monitoring emits one health advisory per silence episode; reception resets it. Transport unavailability never implies escape. Errors/default attributes exclude raw payloads, credentials and network addresses.
- **FR-010**: Provide proper HA entities for room/history, severity/acknowledgement, health, proximity and door light intent. Door intent is red for a latch affecting that door, blue while near, off with fresh local door-node RSSI below threshold, and unknown without such local evidence. Off never guarantees safe opening. Do not automatically change scanner firmware or LED mode.
- **FR-011**: Generate an external private package and document accompanying integration installation. Include private configuration, an initially-off output enable control, acknowledgement action and configurable notification-script/WLED preset bindings. Recheck enablement and storage/processing health before external actions. No hardcoded household channels/entities/credentials. Unknown light intent sends no preset change. Operator presets/scripts own brightness and night schedules. Notification scripts receive an optional private camera/event reference for the current incident, supporting operator-managed snapshot/clip delivery without embedding server URLs or credentials in this project.
- **FR-012**: Use one state machine in HA and tests. Serialize MQTT/contact/tick/ack processing; persist incident transitions before output intents. Bound queues/collections and expose overflow as degraded evidence. Cancel subscriptions/timers/listeners on shutdown. Validate real HA 2026.9.2 lifecycle/schema alongside offline tests.
- **FR-013**: Provide deterministic offline replay and fictional scenarios for boundaries, retained/stale data, cooldown, direct Urgent, internal doors, cross-door isolation, outages/reconnection, recovery gaps, duplicate camera updates, acknowledgement, restart and malformed inputs. Reports/packages require external paths and cannot overwrite input evidence.
- **FR-014**: Document simulation and activation checks. Keep mounting, collar fitting, contact/camera mapping, notification delivery, WLED validation and activation unchecked. Tests establish software behavior, never pet-safety or room-accuracy guarantees.

## Assumptions and deliberate resolutions

The latest operator plan's door colors supersede older issue proposals. Room LEDs
are separate: this delivery exposes room state for custom bindings and preserves
ESPresense firmware status LEDs. Acknowledgement means the incident was seen;
force-clear semantics are not inferred. Camera correlation uses already recorded
door events; missing or reordered input remains missing evidence. Receiver timing
cannot prove radio transmission time. One small custom integration is justified by
retained filtering, restart-safe latches and one testable implementation.

## Success criteria

All software requirements have boundary/runtime tests and independent review. Real
HA accepts and loads the package/integration; synthetic events drive real entities
and stubbed output actions with the enable control obeyed. Tests contact no household
devices and send no household notifications. Physical acceptance stays separate.

Independent incidents at different doors can raise the global maximum severity.
They must each have their own door/camera correlation; affected doors retain red
intent until recovery. The representative door is the origin of the latest severity
increase, and escalation resets acknowledgement.
