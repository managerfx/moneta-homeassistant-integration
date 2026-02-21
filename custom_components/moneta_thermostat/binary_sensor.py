"""Binary sensor entity for the Moneta Thermostat integration.

Mirrors delta-presence.accessory.ts from the Homebridge plugin.
Exposes zone 1 atHome as an occupancy sensor.
"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_ZONE_ID, DOMAIN, MANUFACTURER, MODEL
from .coordinator import MonetaThermostatCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta binary sensor from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MonetaPresenceSensor(coordinator, entry.entry_id)])


class MonetaPresenceSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], BinarySensorEntity
):
    """Occupancy sensor derived from zone 1 atHome.

    Mirrors DeltaPresencePlatformAccessory from delta-presence.accessory.ts.
    """

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_has_entity_name = True
    _attr_name = "Thermostat Presence"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_presence"

    @property
    def icon(self) -> str:
        """Return icon: person inside home when at home, walking away when absent."""
        return "mdi:home-import-outline" if self.is_on else "mdi:home-export-outline"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if someone is home (atHome is True for zone 1)."""
        return self.coordinator.client.get_presence()
