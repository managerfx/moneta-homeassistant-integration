"""The Moneta Thermostat integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MonetaApiClient
from .const import CONF_ACCESS_TOKEN, CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL, DOMAIN
from .coordinator import MonetaThermostatCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
]

# ---------------------------------------------------------------------------
# Service: moneta_thermostat.set_zone_schedule
# ---------------------------------------------------------------------------
# Usage example (via Developer Tools → Services in HA):
#
#   service: moneta_thermostat.set_zone_schedule
#   data:
#     zone_id: "1"
#     step: 30
#     schedule:
#       - day: MON
#         bands:
#           - id: 1
#             setpointType: present
#             start: {hour: 7, min: 0}
#             end: {hour: 22, min: 30}
#       - day: TUE
#         bands: []
#       ... (all 7 days)
# ---------------------------------------------------------------------------

SERVICE_SET_SCHEDULE = "set_zone_schedule"
SERVICE_SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): cv.string,
        vol.Optional("step", default=30): vol.All(int, vol.In([15, 30])),
        vol.Required("schedule"): [
            {
                vol.Required("day"): cv.string,
                vol.Required("bands"): [
                    {
                        vol.Required("id"): int,
                        vol.Required("setpointType"): vol.In(["present", "absent"]),
                        vol.Required("start"): {"hour": int, "min": int},
                        vol.Required("end"): {"hour": int, "min": int},
                    }
                ],
            }
        ],
    }
)


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

    # Ricarica integration quando le opzioni cambiano (es. token aggiornato)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register service (only once, even if multiple entries exist)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        _register_services(hass)

    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register custom services for the domain."""

    async def _handle_set_schedule(call: ServiceCall) -> None:
        """Handle the set_zone_schedule service call."""
        zone_id: str = call.data["zone_id"]
        step: int = call.data.get("step", 30)
        schedule: list[dict] = call.data["schedule"]

        # Apply to all config entries (usually one)
        for coordinator in hass.data.get(DOMAIN, {}).values():
            if isinstance(coordinator, MonetaThermostatCoordinator):
                success = await coordinator.client.set_schedule_by_zone_id(
                    zone_id=zone_id, schedule=schedule, step=step
                )
                if success:
                    await coordinator.async_request_refresh()
                    _LOGGER.info(
                        "Zone %s schedule updated successfully", zone_id
                    )
                else:
                    _LOGGER.error(
                        "Failed to update zone %s schedule", zone_id
                    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        _handle_set_schedule,
        schema=SERVICE_SET_SCHEDULE_SCHEMA,
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options/data change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
