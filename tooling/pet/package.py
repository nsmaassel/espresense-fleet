"""Build a private HA package whose external actions start disabled."""
import re

from custom_components.espresense_pet.config import fields, validate_config

LEVELS = ("heads_up", "suspected", "urgent", "health", "recovered")


def entity(value, domain):
    if not isinstance(value, str) or not re.fullmatch(domain + r"\.[a-z0-9_]{1,64}", value):
        raise ValueError("Invalid output entity")


def validate_bindings(raw, config):
    fields(raw, ("schema",), ("notifications", "lights"))
    if type(raw["schema"]) is not int or raw["schema"] != 1:
        raise ValueError("Unsupported bindings schema")
    notifications, lights = raw.get("notifications", {}), raw.get("lights", {})
    fields(notifications, (), LEVELS)
    for value in notifications.values():
        entity(value, "script")
    fields(lights, (), config["doors"])
    for binding in lights.values():
        fields(binding, ("light_entity", "preset_entity", "off", "blue", "red"))
        entity(binding["light_entity"], "light")
        entity(binding["preset_entity"], "select")
        for color in ("off", "blue", "red"):
            value = binding[color]
            if (not isinstance(value, str) or not 1 <= len(value) <= 64 or not value.strip()
                    or not value.isprintable() or any(token in value for token in ("{{", "{%", "{#"))):
                raise ValueError("Preset names must be bounded plain text")
    return notifications, lights


def state(entity_id, value):
    return {"condition": "state", "entity_id": entity_id, "state": value}


def build_package(raw_config, raw_bindings):
    config = validate_config(raw_config)
    notifications, lights = validate_bindings(raw_bindings, config)
    pet = config["pet_id"]
    enabled = f"input_boolean.{pet}_outputs_enabled"
    health = f"sensor.{pet}_health"
    durable = {"condition": "template", "value_template":
               "{{ state_attr('" + health + "', 'storage_ok') == true and state_attr('" +
               health + "', 'processing_ok') == true }}"}
    package = {
        "espresense_pet": config,
        "input_boolean": {f"{pet}_outputs_enabled": {"name": "Pet advisory outputs", "initial": False}},
        "script": {f"{pet}_acknowledge": {"alias": "Acknowledge pet advisory", "mode": "single",
                                            "sequence": [{"action": "espresense_pet.acknowledge"}]}},
    }
    automations = []
    if notifications:
        choices = []
        for level in LEVELS:
            if level not in notifications:
                continue
            variables = {key: "{{ trigger.event.data." + key + " }}"
                         for key in ("pet_id", "level", "door", "reason")}
            variables["camera_reference"] = "{{ trigger.event.data.get('camera_reference') }}"
            choices.append({"conditions": [{"condition": "template", "value_template":
                                            "{{ trigger.event.data.level == '" + level + "' }}"}],
                            "sequence": [{"action": "script.turn_on", "target": {"entity_id": notifications[level]},
                                          "data": {"variables": variables}}]})
        automations.append({"id": f"{pet}_notifications", "alias": "Pet advisory notifications",
                            "triggers": [{"trigger": "event", "event_type": "espresense_pet_advisory",
                                          "event_data": {"pet_id": pet}}],
                            "actions": [state(enabled, "on"), durable, {"choose": choices}], "mode": "queued", "max": 20})
    for door, binding in sorted(lights.items()):
        intent = f"sensor.{pet}_light_{door}"
        choices = []
        for color in ("off", "blue", "red"):
            sequence = [state(enabled, "on"), durable]
            if color != "off":
                sequence.append({"action": "light.turn_on", "target": {"entity_id": binding["light_entity"]}})
                sequence.append(state(enabled, "on"))
                sequence.append(durable)
            sequence.append({"action": "select.select_option", "target": {"entity_id": binding["preset_entity"]},
                             "data": {"option": binding[color]}})
            choices.append({"conditions": [state(intent, color)], "sequence": sequence})
        automations.append({"id": f"{pet}_light_{door}", "alias": f"Pet advisory light {door}",
                            "triggers": [{"trigger": "state", "entity_id": intent},
                                         {"trigger": "state", "entity_id": enabled, "to": "on"},
                                         {"trigger": "state", "entity_id": health, "attribute": "storage_ok", "to": True}],
                            "actions": [state(enabled, "on"), durable, {"choose": choices}], "mode": "queued", "max": 20})
    if automations:
        package["automation"] = automations
    return package
