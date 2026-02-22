"""Climate entity for the Moneta Thermostat integration.

Design choices (vs Homebridge plugin):
- AUTO mode: target_temperature shows the effective_setpoint (read-only).
  Present/absent setpoints are controlled via separate number entities
  (see number.py), so no TARGET_TEMPERATURE_RANGE here.
- HEAT/COOL mode: target_temperature is settable (manual temp).
- OFF mode: zone is turned off.
- Season-aware: zone 2 is absent in summer → entity becomes unavailable.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CATEGORY_COOLING,
    CATEGORY_HEATING,
    CONF_ZONES_NAMES,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SEASON_SUMMER,
    SEASON_WINTER,
    SETPOINT_ABSENT,
    SETPOINT_PRESENT,
    ZONE_MODE_AUTO,
    ZONE_MODE_HOLIDAY,
    ZONE_MODE_MANUAL,
    ZONE_MODE_OFF,
    ZONE_MODE_PARTY,
)
from .coordinator import MonetaThermostatCoordinator
from .models import Category, SeasonName, Zone, ZoneMode

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode mapping tables
# ---------------------------------------------------------------------------

_HVAC_MODE_PREDICATES = {
    HVACMode.OFF: lambda mode, _season: mode == ZONE_MODE_OFF,
    HVACMode.AUTO: lambda mode, _season: mode in (
        ZONE_MODE_AUTO, ZONE_MODE_HOLIDAY, ZONE_MODE_PARTY
    ),
    HVACMode.HEAT: lambda mode, season: (
        mode == ZONE_MODE_MANUAL and season == SEASON_WINTER
    ),
    HVACMode.COOL: lambda mode, season: (
        mode == ZONE_MODE_MANUAL and season == SEASON_SUMMER
    ),
}

_VALID_MODES_BY_CATEGORY = {
    CATEGORY_HEATING: [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO],
    CATEGORY_COOLING: [HVACMode.OFF, HVACMode.COOL, HVACMode.AUTO],
    "off": [HVACMode.OFF],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moneta climate entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    if not data or not data.zones:
        _LOGGER.error("No zones found in thermostat state")
        return

    zones_names: list[str] = entry.data.get(CONF_ZONES_NAMES, [])

    entities = [
        MonetaClimateEntity(
            coordinator=coordinator,
            zone_id=zone.id,
            display_name=(zones_names[idx] if idx < len(zones_names) else f"Thermostat Zone {zone.id}"),
            entry_id=entry.entry_id,
        )
        for idx, zone in enumerate(data.zones)
    ]
    async_add_entities(entities)


class MonetaClimateEntity(CoordinatorEntity[MonetaThermostatCoordinator], ClimateEntity):
    """Climate entity for a single thermostat zone.

    Present/absent setpoints are managed via number.py entities.
    This entity controls mode (off/auto/heat/cool) and manual temperature only.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    # Only TARGET_TEMPERATURE — no TARGET_TEMPERATURE_RANGE
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        zone_id: str,
        display_name: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._display_name = display_name
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}"
        self._attr_name = display_name

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    # ------------------------------------------------------------------
    # Helper: current zone + state
    # ------------------------------------------------------------------

    @property
    def _zone(self) -> Zone | None:
        data = self.coordinator.data
        if not data:
            return None
        return next((z for z in data.zones if z.id == self._zone_id), None)

    @property
    def available(self) -> bool:
        """False when this zone is absent in the current season payload.

        Zone 2 is only present in winter. In summer the entity is
        marked unavailable so HA doesn't show stale data.
        """
        return self.coordinator.last_update_success and self._zone is not None

    @property
    def _category(self) -> str:
        data = self.coordinator.data
        return data.category if data else "off"

    @property
    def _season(self) -> str:
        data = self.coordinator.data
        return data.season.id if data else SEASON_WINTER

    # ------------------------------------------------------------------
    # HVAC Modes (dynamic based on category)
    # ------------------------------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return _VALID_MODES_BY_CATEGORY.get(self._category, [HVACMode.OFF])

    # ------------------------------------------------------------------
    # Current HVAC mode
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode | None:
        zone = self._zone
        if not zone:
            return None
        season = self._season
        for mode, predicate in _HVAC_MODE_PREDICATES.items():
            if predicate(zone.mode, season):
                return mode
        return HVACMode.OFF

    # ------------------------------------------------------------------
    # Current HVAC action
    # ------------------------------------------------------------------

    @property
    def hvac_action(self) -> HVACAction | None:
        zone = self._zone
        if not zone:
            return None
        category = self._category
        if zone.mode != ZONE_MODE_OFF and category == CATEGORY_HEATING and zone.at_home:
            return HVACAction.HEATING
        if zone.mode != ZONE_MODE_OFF and category == CATEGORY_COOLING and zone.at_home:
            return HVACAction.COOLING
        return HVACAction.IDLE

    # ------------------------------------------------------------------
    # Current temperature
    # ------------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        zone = self._zone
        return zone.temperature if zone else None

    # ------------------------------------------------------------------
    # Target temperature
    #
    # AUTO mode  → shows effective_setpoint (read-only display).
    #              Present/absent temps are managed via number entities.
    # MANUAL mode → shows and accepts the manual setpoint.
    # ------------------------------------------------------------------

    @property
    def target_temperature(self) -> float | None:
        zone = self._zone
        if not zone:
            return None
        return zone.effective_setpoint

    # ------------------------------------------------------------------
    # Temperature limits
    # ------------------------------------------------------------------

    @property
    def min_temp(self) -> float:
        data = self.coordinator.data
        if not data:
            return 5.0
        return min(
            data.limits.absent_min_temp,
            data.manual_limits.min_temp,
        )

    @property
    def max_temp(self) -> float:
        data = self.coordinator.data
        if not data:
            return 30.0
        return max(
            data.limits.absent_max_temp,
            data.manual_limits.max_temp,
        )

    @property
    def target_temperature_step(self) -> float:
        data = self.coordinator.data
        return data.manual_limits.step_value if data else 0.5

    # ------------------------------------------------------------------
    # SET handlers
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await client.set_off()
        elif hvac_mode == HVACMode.AUTO:
            await client.set_auto()
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await client.set_heat_cool()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set manual temperature (only relevant in HEAT/COOL mode).

        In AUTO mode, target_temperature is read-only (shows effective_setpoint).
        To change present/absent setpoints use the number entities.
        """
        zone = self._zone
        if not zone:
            return
        if self.hvac_mode == HVACMode.AUTO:
            # In AUTO, the climate entity doesn't write temperatures.
            # Direction users to the number entities for this.
            _LOGGER.warning(
                "Zone %s is in AUTO mode. Use the number entities to set "
                "present/absent temperatures instead.", self._zone_id
            )
            return

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        data = self.coordinator.data
        if data:
            limits = data.limits
            in_range = limits.present_min_temp <= temperature <= limits.present_max_temp
            temperature = temperature if in_range else limits.present_min_temp
        await self.coordinator.client.set_manual_temperature(self._zone_id, temperature)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Extra state attributes
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict | None:
        """Expose read-only thermostat fields and full schedule as HA attributes."""
        zone = self._zone
        if not zone:
            return None
        attrs: dict = {
            "at_home": zone.at_home,
            "at_home_for_scheduler": zone.at_home_for_scheduler,
            "setpoint_selected": zone.setpoint_selected,
            "holiday_active": zone.holiday_active,
            "effective_setpoint": zone.effective_setpoint,
        }
        # Expose the weekly schedule for visibility (and to allow copying
        # the JSON into the set_zone_schedule service call)
        if zone.calendar:
            attrs["schedule"] = [
                {
                    "day": s.day,
                    "bands": s.bands,
                }
                for s in zone.calendar.schedule
            ]
        return attrs
