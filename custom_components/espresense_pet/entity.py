"""Push entity listener lifecycle; no radio identities in entity attributes."""
from homeassistant.helpers.entity import Entity


class PetEntity(Entity):
    _attr_should_poll = False

    def __init__(self, coordinator, key, platform):
        self.coordinator = coordinator
        self.key = key
        subject = coordinator.config["pet_id"]
        self.entity_id = f"{platform}.{subject}_{key}"
        self._attr_unique_id = f"espresense_pet_{subject}_{key}"
        self._attr_name = f'{coordinator.config["name"]} {key.replace("_", " ")}'

    async def async_added_to_hass(self):
        # Publish output guards before light intents: HA may start automations
        # eagerly while processing a state-change event in the same loop turn.
        priority = -10 if self.key == "health" else 0
        self.async_on_remove(self.coordinator.listen(self.async_write_ha_state, priority=priority))
