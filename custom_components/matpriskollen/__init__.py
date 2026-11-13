"""Matpriskollen: this week's offers on chosen products in chosen stores."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MatpriskollenCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type MatpriskollenConfigEntry = ConfigEntry[MatpriskollenCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: MatpriskollenConfigEntry
) -> bool:
    """Set up from a config entry."""
    coordinator = MatpriskollenCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MatpriskollenConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: MatpriskollenConfigEntry
) -> None:
    """Delete saved offers when the entry is removed."""
    await MatpriskollenCoordinator(hass, entry).async_remove_cache()


async def _async_reload(hass: HomeAssistant, entry: MatpriskollenConfigEntry) -> None:
    """Reload after options or products change."""
    await hass.config_entries.async_reload(entry.entry_id)
