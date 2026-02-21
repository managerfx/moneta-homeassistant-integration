"""Sensor entity for the Moneta Thermostat integration.

Mirrors delta-temperature-sensor.accessory.ts from the Homebridge plugin.
Exposes the external temperature from the thermostat state.
"""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
    """Set up Moneta sensor from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MonetaExternalTemperatureSensor(coordinator, entry.entry_id)])


class MonetaExternalTemperatureSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], SensorEntity
):
    """External temperature sensor.

    Mirrors DeltaTemperatureSensorAccessory from delta-temperature-sensor.accessory.ts.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "External Temperature"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_external_temperature"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> float | None:
        """Return the external temperature from the thermostat root state."""
        data = self.coordinator.data
        return data.external_temperature if data else None
