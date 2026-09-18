"""Recent-indoor history and conservative local door proximity."""
from homeassistant.components.binary_sensor import BinarySensorEntity

from .coordinator import DOMAIN
from .entity import PetEntity


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]
    keys = ["recently_seen"] + [f"near_{door}" for door in coordinator.config["doors"]]
    async_add_entities([PetBinarySensor(coordinator, key) for key in keys])


class PetBinarySensor(PetEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key, "binary_sensor")

    @property
    def is_on(self):
        if self.key == "recently_seen":
            return self.coordinator.state["recently_seen"]
        return self.coordinator.state["doors"][self.key[5:]]["near"]
