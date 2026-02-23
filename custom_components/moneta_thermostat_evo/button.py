"""Button entities for the Moneta Thermostat integration.

Exposes a refresh button to force an immediate state update from the API,
bypassing the normal polling interval.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MonetaThermostatCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta button entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MonetaRefreshButton(coordinator, entry.entry_id),
    ])


class MonetaRefreshButton(
    CoordinatorEntity[MonetaThermostatCoordinator], ButtonEntity
):
    """Button to force an immediate refresh of thermostat state.
    
    Useful when you want to see the latest state without waiting
    for the next polling interval.
    """

    _attr_has_entity_name = True
    _attr_name = "Refresh State"
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_refresh_button"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_press(self) -> None:
        """Handle the button press - force refresh from API."""
        _LOGGER.info("Manual refresh triggered for Moneta Thermostat")
        # Invalidate cache to force fresh data fetch
        self.coordinator.client._invalidate_cache()
        await self.coordinator.async_request_refresh()
