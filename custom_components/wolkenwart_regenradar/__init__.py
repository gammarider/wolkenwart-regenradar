"""Independent Home Assistant integration for DWD radar forecasts."""

from homeassistant.const import Platform

from .coordinator import RadarCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass, entry):
    coordinator = RadarCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        # Load diagnostics even when the first DWD request fails.
        await coordinator.async_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_shutdown()
        raise
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        return True
    return False
