"""HA input subscriptions normalize data before entering the bounded queue."""
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .ingress import camera_events, device_observation


async def subscribe(coordinator):
    hass, config = coordinator.hass, coordinator.config
    if not await mqtt.async_wait_for_mqtt_client(hass):
        return False

    @callback
    def status(connected):
        coordinator.transport_status(connected)

    coordinator.unsubscribers.append(mqtt.async_subscribe_connection_status(hass, status))
    status(mqtt.is_connected(hass))  # No await between registration and initial sample.

    for node, mapping in config["nodes"].items():
        topic = f'espresense/devices/{config["device_alias"]}/{mapping["mqtt_room"]}'

        @callback
        def observation(message, node=node, expected=topic):
            now = coordinator.clock()
            if message.topic != expected:
                return
            normalized = device_observation(message.payload, message.retain)
            if normalized is not None:
                coordinator.enqueue("observe", (node, *normalized), now)

        coordinator.unsubscribers.append(await mqtt.async_subscribe(hass, topic, observation, qos=0))

    @callback
    def camera(message):
        now = coordinator.clock()
        if message.topic != config["frigate_topic"]:
            return
        for event in camera_events(message.payload, message.retain, config,
                                   wall_now=coordinator.wall(), monotonic_now=now):
            coordinator.enqueue("camera", (event["door"], event["zone"], event["event_id"], event["evidence_at"]), now)

    coordinator.unsubscribers.append(await mqtt.async_subscribe(hass, config["frigate_topic"], camera, qos=0))
    contacts = {mapping["contact"]: door for door, mapping in config["doors"].items()}

    @callback
    def contact(event):
        now = coordinator.clock()
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is not None and new is not None and old.state == "off" and new.state == "on":
            coordinator.enqueue("door_open", (contacts[event.data["entity_id"]],), now)

    coordinator.unsubscribers.append(async_track_state_change_event(hass, contacts, contact))

    @callback
    def tick(_when):
        coordinator.enqueue("advance", (), coordinator.clock())

    coordinator.unsubscribers.append(async_track_time_interval(hass, tick, timedelta(seconds=1), cancel_on_shutdown=True))
    return True
