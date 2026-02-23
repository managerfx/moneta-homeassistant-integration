"""Sensor entities for the Moneta Thermostat integration.

Exposes:
- External temperature (from thermostat root state)
- Per-zone temperature sensors (one per zone)
- Active scheduling status (indicates if there are active schedulations)
- First zone schedule display (human-readable format)

Zone sensors become unavailable when the zone is absent from the
current season payload (e.g. zone 2 in summer).
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
from .models import Band, Zone

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta sensor entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        MonetaExternalTemperatureSensor(coordinator, entry.entry_id),
        MonetaActiveSchedulingSensor(coordinator, entry.entry_id),
        MonetaFirstZoneScheduleSensor(coordinator, entry.entry_id),
    ]

    # Create one temperature sensor per zone found at startup.
    # Entities become 'unavailable' if the zone disappears (season change).
    data = coordinator.data
    if data:
        for zone in data.zones:
            entities.append(
                MonetaZoneTemperatureSensor(coordinator, entry.entry_id, zone.id)
            )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# External temperature sensor
# ---------------------------------------------------------------------------

class MonetaExternalTemperatureSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], SensorEntity
):
    """External temperature sensor (from thermostat root state)."""

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


# ---------------------------------------------------------------------------
# Per-zone temperature sensor
# ---------------------------------------------------------------------------

class MonetaZoneTemperatureSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], SensorEntity
):
    """Temperature sensor for a single thermostat zone.

    Zone sensors become unavailable when the zone is absent from the
    payload (e.g. zone 2 in summer, which only has zones 1 and 3).
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
        zone_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}_temperature"
        self._attr_name = f"Zone {zone_id} Temperature"

    @property
    def _zone(self) -> Zone | None:
        data = self.coordinator.data
        if not data:
            return None
        return next((z for z in data.zones if z.id == self._zone_id), None)

    @property
    def available(self) -> bool:
        """False when this zone is absent in the current season payload."""
        return self.coordinator.last_update_success and self._zone is not None

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
        zone = self._zone
        return zone.temperature if zone else None

    @property
    def extra_state_attributes(self) -> dict | None:
        zone = self._zone
        if not zone:
            return None
        return {
            "effective_setpoint": zone.effective_setpoint,
            "mode": zone.mode,
            "at_home": zone.at_home,
            "setpoint_selected": zone.setpoint_selected,
        }


# ---------------------------------------------------------------------------
# Active scheduling sensor
# ---------------------------------------------------------------------------

class MonetaActiveSchedulingSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], SensorEntity
):
    """Sensor that indicates if there are active schedulations."""

    _attr_has_entity_name = True
    _attr_name = "Active Scheduling"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_active_scheduling"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> str:
        """Return whether there are active schedulations."""
        data = self.coordinator.data
        if not data:
            return "unknown"
        
        # Check if any zone has a non-empty schedule
        for zone in data.zones:
            if zone.calendar and zone.calendar.schedule:
                for day_schedule in zone.calendar.schedule:
                    if day_schedule.bands:
                        return "active"
        
        return "inactive"


# ---------------------------------------------------------------------------
# First zone schedule sensor
# ---------------------------------------------------------------------------

class MonetaFirstZoneScheduleSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], SensorEntity
):
    """Sensor that displays the schedule of the first zone in a readable format."""

    _attr_has_entity_name = True
    _attr_name = "First Zone Schedule"
    _attr_icon = "mdi:calendar-text"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_first_zone_schedule"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def _format_time(self, hour: int, minute: int) -> str:
        """Format time as HH:MM."""
        return f"{hour:02d}:{minute:02d}"

    def _format_band(self, band: Band) -> str:
        """Format a single band as start-end."""
        start = self._format_time(band.start_hour, band.start_min)
        end = self._format_time(band.end_hour, band.end_min)
        return f"{start}-{end}"

    @property
    def native_value(self) -> str:
        """Return the schedule of the first zone in a human-readable format."""
        data = self.coordinator.data
        if not data or not data.zones:
            return "No schedule available"
        
        # Get the first zone
        first_zone = data.zones[0]
        if not first_zone.calendar or not first_zone.calendar.schedule:
            return "No schedule available"
        
        # Build a readable schedule format
        schedule_lines = []
        for day_schedule in first_zone.calendar.schedule:
            if not day_schedule.bands:
                continue
            
            # Format bands for this day
            bands_str = ", ".join([self._format_band(band) for band in day_schedule.bands])
            schedule_lines.append(f"{day_schedule.day} {bands_str}")
        
        if not schedule_lines:
            return "No active schedule"
        
        return "; ".join(schedule_lines)
