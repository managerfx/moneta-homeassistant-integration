"""Number entities for the Moneta Thermostat integration.

Exposes per-zone present and absent setpoint temperatures as HA number
entities, allowing the user to set them independently from the climate
entity (which only controls mode and manual temperature).

Zone numbers become unavailable when the zone is absent from the current
season payload (e.g. zone 2 in summer).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, SETPOINT_ABSENT, SETPOINT_PRESENT
from .coordinator import MonetaThermostatCoordinator
from .models import Zone

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta number entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    if not data:
        return

    limits = data.limits
    entities: list[NumberEntity] = []

    # Handle Present Setpoint
    if limits.present_is_unique:
        entities.append(
            MonetaSetpointNumber(
                coordinator, entry.entry_id, "1", SETPOINT_PRESENT, is_global=True
            )
        )
    else:
        for zone in data.zones:
            entities.append(
                MonetaSetpointNumber(coordinator, entry.entry_id, zone.id, SETPOINT_PRESENT)
            )

    # Handle Absent Setpoint
    if limits.absent_is_unique:
        entities.append(
            MonetaSetpointNumber(
                coordinator, entry.entry_id, "1", SETPOINT_ABSENT, is_global=True
            )
        )
    else:
        for zone in data.zones:
            entities.append(
                MonetaSetpointNumber(coordinator, entry.entry_id, zone.id, SETPOINT_ABSENT)
            )

    async_add_entities(entities)


class MonetaSetpointNumber(
    CoordinatorEntity[MonetaThermostatCoordinator], NumberEntity
):
    """Number entity to set either the 'present' or 'absent' setpoint for a zone.

    These correspond to the two temperature profiles the thermostat uses:
      - present: temperature used when someone is home
      - absent:  temperature used when away (eco/setback)

    Changes are sent immediately via the API.
    Entities become unavailable when the zone is missing (season change).
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
        zone_id: str,
        setpoint_type: str,  # "present" or "absent"
        is_global: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._zone_id = zone_id
        self._setpoint_type = setpoint_type
        self._is_global = is_global

        label = "Present" if setpoint_type == SETPOINT_PRESENT else "Absent"
        if is_global:
            self._attr_unique_id = f"{entry_id}_global_{setpoint_type}_setpoint"
            self._attr_name = f"{label} Temperature"
        else:
            self._attr_unique_id = f"{entry_id}_zone_{zone_id}_{setpoint_type}_setpoint"
            self._attr_name = f"Zone {zone_id} {label} Temperature"

    @property
    def _zone(self) -> Zone | None:
        data = self.coordinator.data
        if not data:
            return None
        return next((z for z in data.zones if z.id == self._zone_id), None)

    @property
    def available(self) -> bool:
        """False when this zone is absent from the current season payload."""
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
    def native_min_value(self) -> float:
        data = self.coordinator.data
        if not data:
            return 5.0
        limits = data.limits
        if self._setpoint_type == SETPOINT_PRESENT:
            return limits.present_min_temp
        return limits.absent_min_temp

    @property
    def native_max_value(self) -> float:
        data = self.coordinator.data
        if not data:
            return 30.0
        limits = data.limits
        if self._setpoint_type == SETPOINT_PRESENT:
            return limits.present_max_temp
        return limits.absent_max_temp

    @property
    def native_step(self) -> float:
        data = self.coordinator.data
        return data.limits.step_value if data else 0.5

    @property
    def native_value(self) -> float | None:
        """Return the current temperature for this setpoint type."""
        zone = self._zone
        if not zone:
            return None
        sp = next((s for s in zone.setpoints if s.type == self._setpoint_type), None)
        return sp.temperature if sp else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the setpoint temperature via API."""
        client = self.coordinator.client
        if self._setpoint_type == SETPOINT_PRESENT:
            await client.set_present_absent_temperature(
                self._zone_id, present_temperature=value
            )
        else:
            await client.set_present_absent_temperature(
                self._zone_id, absent_temperature=value
            )
        await self.coordinator.async_request_refresh()
