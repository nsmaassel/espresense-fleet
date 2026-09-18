# Pet advisory integration research

Verified 2026-09-18 against official documentation and the installed Home Assistant
2026.9.2 Python package. These are software contracts and design decisions, not
evidence that a real collar, camera, door or notification works.

## Architecture decision

Use one small custom integration with a pure, injected-time state machine and a
generated Home Assistant package. The package provides configuration, acknowledgement
and initially disabled output bindings; it does not reproduce incident policy in
templates. Retained filtering, continuous freshness, ordered persistence and incident
recovery justify the Python boundary. Offline replay must execute this same engine.

The MQTT automation trigger exposes topic, payload, QoS and parsed JSON, but does
not expose the retain flag. The lower-level integration message does expose it.
This makes a YAML-only retained-rejection claim unsound for the pinned version.
[Trigger source](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/trigger.py),
[message model](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/models.py).

## MQTT lifecycle: exact installed contracts

1. First call `await mqtt.async_wait_for_mqtt_client(hass)`. False means no enabled
   MQTT entry or setup did not become available; the internal setup wait is bounded
   to 50 seconds. True means a client exists, not that it is connected.
2. Register `mqtt.async_subscribe_connection_status(hass, callback)`. This synchronous
   function returns an unsubscribe callback and does not deliver the initial value.
3. Immediately sample `mqtt.is_connected(hass)` without an intervening await.
   Registering the listener first avoids losing a connection change around startup.
   Feed the snapshot and subsequent boolean changes through the ordered coordinator;
   repeated identical status must not reset monitoring timers.
4. Subscribe with `await mqtt.async_subscribe(hass, topic, callback, qos=0)` and retain
   each returned unsubscribe callback. Client absence or a disabled entry raises an
   exception; do not log it verbatim because its context may contain the topic.

`is_connected` reads the client's current boolean and requires initialized MQTT
data. The client sets that boolean before dispatching connection changes. A connected
broker session is not proof of node health, camera health or accepted subscriptions.
The subscription call does not wait for a broker SUBACK.
[MQTT public API](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/__init__.py),
[startup guard](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/util.py),
[subscription and connection implementation](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/client.py).

Received messages have `topic`, `payload`, `qos`, `retain`, `subscribed_topic` and
`timestamp`. Reject retained observations before parsing or changing domain state.
Capture monotonic receipt time before queueing; queue latency must not manufacture
freshness. ESPresense payloads have no radio observation timestamp, so delayed
non-retained delivery remains a documented limitation.
[HA message model](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/mqtt/models.py),
[ESPresense v4.0.6 payload](https://github.com/ESPresense/ESPresense/blob/v4.0.6/src/BleFingerprint.cpp).

## Storage, entities and scheduling

Use `Store(hass, 1, key, private=True, atomic_writes=True)` and its asynchronous
`async_load`/`async_save` methods. Validate restored data independently of live
configuration. Persist incident metadata, acknowledgement and bounded camera
deduplication history; restore no positive radio freshness or recovery interval.
Serialize transitions and save before emitting their output intents. A failed save
must expose degraded durability and must not silently clear an existing latch.
[Store source](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/helpers/storage.py).

`async_track_time_interval(hass, callback, timedelta(seconds=1),
cancel_on_shutdown=True)` returns a cancellation callback and passes UTC datetime
to the callback. Domain elapsed-time calculations should still use the injected
monotonic clock. Startup and reconnect deliberately begin a new monitored-silence
interval under this feature's policy; unavailable time is not observed silence.
[Event helpers](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/helpers/event.py).

YAML-driven platforms can use `discovery.async_load_platform(hass, platform,
DOMAIN, discovery_info, config)` and `async_setup_platform(hass, config,
async_add_entities, discovery_info=None)`. Supply the real HA configuration.
Use proper SensorEntity/BinarySensorEntity implementations, stable unique IDs and
`should_poll=False`; push changes with `async_write_ha_state`. Clean up listeners
when entities are removed and integration resources on shutdown.
[Platform loader](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/helpers/discovery.py),
[push entities](https://developers.home-assistant.io/docs/integration_fetching_data/).

Register the acknowledgement service through `hass.services.async_register` with
a validated schema and `services.yaml` description. Acknowledgement records that
an incident was seen; it does not assert return or force-clear the incident.
[Custom service actions](https://developers.home-assistant.io/docs/dev_101_services/).

## Freshness and camera interpretation

HA `last_changed` changes with the state; `last_updated` also changes with attributes;
`last_reported` changes on every state write. The first two do not establish receipt
freshness when reports repeat identical values. MQTT room presence exposes a room
estimate with configurable timeout/away timeout; it is not an incident state machine.
[State timestamps](https://www.home-assistant.io/docs/configuration/state_object/),
[MQTT room](https://www.home-assistant.io/integrations/mqtt_room/).

Use Frigate object events and validate `type`, `after.id`, `after.camera`,
`after.label`, `after.false_positive`, `after.frame_time`, `after.current_zones`
and `after.end_time`. Updates can reuse an event ID when a zone or snapshot changes.
Historical `entered_zones` does not mean current occupancy. Ended events are not
fresh sightings. Compare observation time with the recorded opening of that same
door, and reject stale/future frames. A class label of cat does not identify the
enrolled animal. Deduplication must distinguish an inside-stage event from a later
outside-stage update, while preventing repeated stage evidence after recovery.
[Frigate MQTT contract](https://docs.frigate.video/integrations/mqtt/).

## Package and output contracts

Load packages with `homeassistant: packages: !include_dir_named packages`; helper
keys must be unique across packages and the main configuration. Bind outputs to
operator-supplied scripts/presets and gate them behind the disabled control.
[Packages](https://www.home-assistant.io/docs/configuration/packages/).

Direct `script.NAME` calls wait and propagate errors; `script.turn_on` starts work
without waiting. WLED presets use `light.turn_on`, then `select.select_option` on
the preset entity. Subsequent light-state changes may clear the preset selection.
Unknown intent should issue no preset change.
[Scripts](https://www.home-assistant.io/integrations/script/),
[WLED](https://www.home-assistant.io/integrations/wled/).

Helpers restore prior state when `initial` is omitted. Input text is limited to
255 characters. State/template `for` waits reset on restart or automation reload;
restored timers do not replay `timer.finished` when expiration occurred offline.
These helpers remain useful for operator controls, but are not the incident store.
[Datetime](https://www.home-assistant.io/integrations/input_datetime/),
[boolean](https://www.home-assistant.io/integrations/input_boolean/),
[select](https://www.home-assistant.io/integrations/input_select/),
[text](https://www.home-assistant.io/integrations/input_text/),
[timer](https://www.home-assistant.io/integrations/timer/),
[trigger timing](https://www.home-assistant.io/docs/automation/trigger/).

## Verification and preimplementation review

Every FR-001 through FR-014 maps to an implementation or validation task. No
constitutional conflict was identified. The owning spec resolved four gaps raised
by review: persist bounded camera deduplication across restart;
retain every affected door when incidents involve multiple doors; restrict heads-up
advisories to exterior doors; and define tied nearest nodes in the same room as one
room candidate. Finite deduplication history must not claim indefinite replay protection.

Run generated YAML through real HA 2026.9.2 `check_config`. Then exercise the actual
integration, entities, services and persistence in a disposable Linux HA runtime,
with synthetic MQTT/contact events and stub output services. Configuration acceptance
alone is insufficient. Pure engine tests should cover exact freshness/hold/correlation
boundaries; runtime tests cover startup already-connected/disconnected, reconnect,
identical reports, retained rejection, storage failures, acknowledgement, output
enable gating and shutdown cleanup. No test requires household devices or credentials.
[Container configuration check](https://www.home-assistant.io/common-tasks/container/),
[HA testing guidance](https://developers.home-assistant.io/docs/development_testing/),
[official MQTT/time test helpers](https://github.com/home-assistant/core/blob/2026.9.2/tests/common.py).

Actual collar performance, mapping correctness, notification delivery and WLED
operation remain physical acceptance work. Software tests provide no containment,
universal room-accuracy or pet-safety guarantee.
