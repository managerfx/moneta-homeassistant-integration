"""Climate entity for the Moneta Thermostat integration.

Mirrors the business logic in delta-thermostat.accessory.ts from the
Homebridge plugin, adapted to the Home Assistant climate platform.
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
    DEFAULT_ZONE_ID,
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
# Mode mapping tables (mirrors ZONE_MODE_TO_TARGET_STATE_MAP in TS plugin)
# ---------------------------------------------------------------------------
# Maps HA HVACMode → logic predicate(zone_mode, season) that returns True
# Order matters: checked in HA HVACMode list order
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

# Maps Category (heating/cooling) → valid HVACModes
# Mirrors VALID_TARGET_STATE_BY_CATEGORY_MAP in TS plugin
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

    Mirrors DeltaThermostatPlatformAccessory from delta-thermostat.accessory.ts.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True

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
    def _category(self) -> str:
        data = self.coordinator.data
        return data.category if data else "off"

    @property
    def _season(self) -> str:
        data = self.coordinator.data
        return data.season.id if data else SEASON_WINTER

    # ------------------------------------------------------------------
    # HVAC Modes (dynamic based on category – same as Homebridge plugin)
    # ------------------------------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return _VALID_MODES_BY_CATEGORY.get(self._category, [HVACMode.OFF])

    # ------------------------------------------------------------------
    # Feature flags (dynamic: target_temp_range only in AUTO mode)
    # ------------------------------------------------------------------

    @property
    def supported_features(self) -> ClimateEntityFeature:
        base = ClimateEntityFeature.TARGET_TEMPERATURE
        if self.hvac_mode == HVACMode.AUTO:
            base |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return base

    # ------------------------------------------------------------------
    # Current HVAC mode (mirrors handleTargetHeatingCoolingStateGet)
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
    # Current HVAC action (mirrors getCurrentHeatingCoolingState)
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
    # Current temperature (mirrors handleCurrentTemperatureGet)
    # ------------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        zone = self._zone
        return zone.temperature if zone else None

    # ------------------------------------------------------------------
    # Target temperature – MANUAL mode (mirrors handleTargetTemperatureGet)
    # ------------------------------------------------------------------

    @property
    def target_temperature(self) -> float | None:
        zone = self._zone
        if not zone or self.hvac_mode == HVACMode.AUTO:
            return None
        return zone.effective_setpoint

    # ------------------------------------------------------------------
    # Target temperature HIGH – AUTO mode (mirrors CoolingThresholdTemperature)
    #
    # Heating season → highest desired temp = present setpoint (you want it
    #   warmer when home, so this is the "upper bound")
    # Cooling season → highest desired temp = absent setpoint
    # ------------------------------------------------------------------

    @property
    def target_temperature_high(self) -> float | None:
        zone = self._zone
        if not zone or self.hvac_mode != HVACMode.AUTO:
            return None
        category = self._category
        client = self.coordinator.client
        if category == CATEGORY_HEATING:
            temp = client.get_setpoint_temperature(zone, SETPOINT_PRESENT)
            if temp is not None:
                return max(temp, zone.effective_setpoint)
            return zone.effective_setpoint
        if category == CATEGORY_COOLING:
            return client.get_setpoint_temperature(zone, SETPOINT_ABSENT)
        return None

    # ------------------------------------------------------------------
    # Target temperature LOW – AUTO mode (mirrors HeatingThresholdTemperature)
    #
    # Heating season → lowest desired temp = absent setpoint (away temp)
    # Cooling season → lowest desired temp = present setpoint
    # ------------------------------------------------------------------

    @property
    def target_temperature_low(self) -> float | None:
        zone = self._zone
        if not zone or self.hvac_mode != HVACMode.AUTO:
            return None
        category = self._category
        client = self.coordinator.client
        if category == CATEGORY_HEATING:
            return client.get_setpoint_temperature(zone, SETPOINT_ABSENT)
        if category == CATEGORY_COOLING:
            return client.get_setpoint_temperature(zone, SETPOINT_PRESENT)
        return None

    # ------------------------------------------------------------------
    # Temperature limits (from limits / manual_limits)
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
        """Set HVAC mode. Mirrors handleTargetHeatingCoolingStateSet."""
        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await client.set_off()
        elif hvac_mode == HVACMode.AUTO:
            await client.set_auto()
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await client.set_heat_cool()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set temperature. Mirrors handleTargetTemperatureSet and threshold handlers."""
        zone = self._zone
        if not zone:
            return

        client = self.coordinator.client
        hvac_mode = self.hvac_mode

        if hvac_mode == HVACMode.AUTO:
            # AUTO mode: set present/absent setpoints
            high = kwargs.get("target_temp_high")
            low = kwargs.get("target_temp_low")
            category = self._category
            if category == CATEGORY_HEATING:
                # high → present (CoolingThreshold), low → absent (HeatingThreshold)
                await client.set_present_absent_temperature(
                    self._zone_id,
                    present_temperature=high,
                    absent_temperature=low,
                )
            else:
                # COOLING: low → present, high → absent
                await client.set_present_absent_temperature(
                    self._zone_id,
                    present_temperature=low,
                    absent_temperature=high,
                )
        else:
            # MANUAL mode: validate against limits then set
            temperature = kwargs.get(ATTR_TEMPERATURE)
            if temperature is None:
                return
            data = self.coordinator.data
            if data:
                limits = data.limits
                in_range = limits.present_min_temp <= temperature <= limits.present_max_temp
                temperature = temperature if in_range else limits.present_min_temp
            await client.set_manual_temperature(self._zone_id, temperature)

        await self.coordinator.async_request_refresh()
