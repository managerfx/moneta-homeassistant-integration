"""Binary sensor entities for the Moneta Thermostat integration.

Exposes:
- Presence (atHome from zone 1) — occupancy sensor
- Holiday mode (holidayActive from zone 1) — vacation mode active
- Party mode (mode=party from zone 1) — party/boost mode active

These sensors reflect the current state from the thermostat.
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
from .models import ZoneMode

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta binary sensor entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MonetaPresenceSensor(coordinator, entry.entry_id),
        MonetaHolidaySensor(coordinator, entry.entry_id),
        MonetaPartySensor(coordinator, entry.entry_id),
    ])


class MonetaPresenceSensor(
    CoordinatorEntity[MonetaThermostatCoordinator], BinarySensorEntity
):
    """Occupancy sensor derived from zone 1 atHome.

    True  = someone is home (physical thermostat shows person inside).
    False = away mode (physical thermostat shows person outside).

    READ-ONLY: cannot be set via API.
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
        """Return True if zone 1 atHome is True."""
        return self.coordinator.client.get_presence()

    @property
    def extra_state_attributes(self) -> dict | None:
        """Expose atHomeForScheduler as attribute for automations."""
        zone = self.coordinator.client.get_zone_by_id(DEFAULT_ZONE_ID)
        if not zone:
            return None
        return {"at_home_for_scheduler": zone.at_home_for_scheduler}


class MonetaHolidaySensor(
    CoordinatorEntity[MonetaThermostatCoordinator], BinarySensorEntity
):
    """Binary sensor for holiday mode (holidayActive field).

    True  = holiday mode active (physical thermostat vacation button).
    False = normal operation.

    READ-ONLY: cannot be set via API.
    """

    _attr_has_entity_name = True
    _attr_name = "Holiday Mode"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_holiday"

    @property
    def icon(self) -> str:
        return "mdi:beach" if self.is_on else "mdi:home-clock"

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
        """Return True if zone 1 holidayActive is True."""
        zone = self.coordinator.client.get_zone_by_id(DEFAULT_ZONE_ID)
        return zone.holiday_active if zone else False


class MonetaPartySensor(
    CoordinatorEntity[MonetaThermostatCoordinator], BinarySensorEntity
):
    """Binary sensor for party mode (mode=party).

    True  = party mode active (comfort temperature override).
    False = normal operation.
    """

    _attr_has_entity_name = True
    _attr_name = "Party Mode"

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_party"

    @property
    def icon(self) -> str:
        return "mdi:party-popper" if self.is_on else "mdi:calendar-clock"

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
        """Return True if zone 1 mode is party."""
        zone = self.coordinator.client.get_zone_by_id(DEFAULT_ZONE_ID)
        return zone.mode == ZoneMode.PARTY if zone else False

    @property
    def extra_state_attributes(self) -> dict | None:
        """Expose expiration info for party mode."""
        zone = self.coordinator.client.get_zone_by_id(DEFAULT_ZONE_ID)
        if not zone or zone.mode != ZoneMode.PARTY:
            return None
        return {
            "expiration_minutes": zone.expiration,
            "date_expiration": zone.date_expiration,
        }
