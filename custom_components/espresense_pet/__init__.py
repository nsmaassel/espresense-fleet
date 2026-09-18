"""ESPresense pet advisories; framework imports belong to runtime setup."""


def CONFIG_SCHEMA(config):
    """Keep importing the pure domain possible without HA or Voluptuous installed."""
    import voluptuous as vol
    from .config import validate_config

    try:
        return {**config, "espresense_pet": validate_config(config["espresense_pet"])}
    except (ValueError, KeyError, TypeError):
        raise vol.Invalid("Invalid private pet advisory configuration") from None


async def async_setup(hass, config):
    from homeassistant.helpers import discovery
    from .coordinator import Coordinator, DOMAIN

    if DOMAIN in hass.data:
        return False
    coordinator = Coordinator(hass, config[DOMAIN])
    if not await coordinator.async_start():
        return False
    hass.data[DOMAIN] = coordinator
    for platform in ("sensor", "binary_sensor"):
        await discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
    return True
