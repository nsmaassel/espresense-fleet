"""Diagnostic rooms, latched incident, health, per-door light intents and levels."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .coordinator import DOMAIN
from .entity import PetEntity


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]
    doors = coordinator.config["doors"]
    keys = ["room", "last_room", "alert", "health"] + [f"light_{door}" for door in doors]
    keys += [f"level_{door}" for door, definition in doors.items() if definition.get("levels")]
    async_add_entities([PetSensor(coordinator, key) for key in keys])


class PetSensor(PetEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key, "sensor")
        if key.startswith("level_"):
            levels = coordinator.config["doors"][key[6:]]["levels"]
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["escape", "unknown", "off", *(level["name"] for level in levels)]

    @property
    def native_value(self):
        state = self.coordinator.state
        if self.key == "alert":
            return state["alert"]["level"]
        if self.key.startswith("light_"):
            return state["doors"][self.key[6:]]["light"]
        if self.key.startswith("level_"):
            return state["doors"][self.key[6:]]["level"]
        return state[self.key]

    @property
    def extra_state_attributes(self):
        if self.key == "alert":
            alert = self.coordinator.state["alert"]
            return {"acknowledged": alert["acknowledged"], "affected_doors": list(alert["doors"]), "door": alert["door"]}
        if self.key == "health":
            return {"storage_ok": self.coordinator.storage_ok, "overflow": self.coordinator.overflow,
                    "processing_ok": self.coordinator.processing_ok}
        if self.key in ("room", "last_room"):
            return {"last_seen_age_s": self.coordinator.state["last_seen_age_s"]}
        return None
