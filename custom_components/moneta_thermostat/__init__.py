"""The Moneta Thermostat integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MonetaApiClient
from .const import CONF_ACCESS_TOKEN, CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL, DOMAIN
from .coordinator import MonetaThermostatCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Moneta Thermostat from a config entry."""
    session = async_get_clientsession(hass)
    client = MonetaApiClient(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        session=session,
        polling_interval_minutes=entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
    )

    coordinator = MonetaThermostatCoordinator(
        hass=hass,
        client=client,
        polling_interval_minutes=entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
    )

    # Fetch initial data before setting up platforms
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
