"""Climate entity for the Moneta Thermostat integration.

DESIGN:
- HVAC modes: off / heat (winter) / cool (summer) / auto
- In AUTO mode, preset_mode selects the operating profile:
    - "Pianificazione"        → mode=auto  (follows weekly schedule)
    - "Fuori casa"            → mode=auto + absent setpoint applied manually
    - "Boost"                 → mode=party (high comfort temp)
    - "Protezione antigelo"   → mode=off   (frost protection, lowest setpoint)
- In HEAT/COOL mode: target_temperature is the manual setpoint (settable).
- In AUTO mode: target_temperature shows effective_setpoint (read-only display).
- Present/absent setpoints are managed via separate number entities (number.py).
- Zone 2 becomes unavailable in summer (season change handling).
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
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_HOME,
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
)
from .coordinator import MonetaThermostatCoordinator
from .models import Zone, ZoneMode

_LOGGER = logging.getLogger(__name__)

# Sentinel used to distinguish "no optimistic preset set" from "preset is None"
_SENTINEL_PRESET: str | None = object()  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Preset constants — use HA standard values for icons
# PRESET_HOME, PRESET_BOOST, PRESET_AWAY are imported from HA for standard icons
# Label translations are provided via strings.json / translations/*.json
# ---------------------------------------------------------------------------
# PRESET_HOME = "home"        # imported - mode=auto (Schedule/Pianificazione)
# PRESET_BOOST = "boost"      # DISABLED - Party mode broken in backend
# PRESET_AWAY = "away"        # DISABLED - Holiday mode broken in backend

# Only Schedule preset is available - Party and Holiday disabled due to backend API issues
ALL_PRESETS = [PRESET_HOME]

# Maps zone.mode → preset value
_MODE_TO_PRESET: dict[str, str | None] = {
    ZoneMode.AUTO: PRESET_HOME,
    ZoneMode.PARTY: PRESET_BOOST,
    ZoneMode.HOLIDAY: PRESET_AWAY,
    ZoneMode.OFF: None,
    ZoneMode.MANUAL: None,
}

# ---------------------------------------------------------------------------
# HVAC mode predicates
# ---------------------------------------------------------------------------
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
            display_name=(
                zones_names[idx]
                if idx < len(zones_names)
                else f"Thermostat Zone {zone.id}"
            ),
            entry_id=entry.entry_id,
        )
        for idx, zone in enumerate(data.zones)
    ]
    async_add_entities(entities)


class MonetaClimateEntity(CoordinatorEntity[MonetaThermostatCoordinator], ClimateEntity):
    """Climate entity for a single thermostat zone.

    Presets (in AUTO hvac_mode):
        schedule  [🕐] → follows the weekly schedule calendar (mode=auto)
        away      [🚶] → away mode (atHome=false on physical device; mode=auto)
        boost     [🔥] → party/boost mode (mode=party)

    Present/absent setpoints are managed via number.py entities.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_translation_key = "thermostat_zone"
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = ALL_PRESETS

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

        # Optimistic state – cleared when coordinator delivers real data
        self._optimistic_hvac_mode: HVACMode | None = None
        self._optimistic_target_temp: float | None = None
        self._optimistic_preset_mode: str | None = _SENTINEL_PRESET

    # ------------------------------------------------------------------
    # Optimistic helpers
    # ------------------------------------------------------------------

    def _clear_optimistic(self) -> None:
        """Reset all optimistic overrides."""
        self._optimistic_hvac_mode = None
        self._optimistic_target_temp = None
        self._optimistic_preset_mode = _SENTINEL_PRESET

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when fresh backend data arrives."""
        self._clear_optimistic()
        super()._handle_coordinator_update()

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
    # Internal helpers
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

        Zone 2 is only present in winter; in summer the entity is
        unavailable so HA doesn't show stale data.
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
    # HVAC modes
    # ------------------------------------------------------------------

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return _VALID_MODES_BY_CATEGORY.get(self._category, [HVACMode.OFF])

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        zone = self._zone
        if not zone:
            return None
        # OFF or MANUAL → direct mapping
        if zone.mode == ZoneMode.OFF:
            return HVACMode.OFF
        if zone.mode == ZoneMode.MANUAL:
            season = self._season
            return HVACMode.HEAT if season == SEASON_WINTER else HVACMode.COOL
        # auto / party / holiday → AUTO (preset distinguishes them)
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction | None:
        zone = self._zone
        if not zone:
            return None
        category = self._category
        if zone.mode != ZoneMode.OFF and category == CATEGORY_HEATING and zone.at_home:
            return HVACAction.HEATING
        if zone.mode != ZoneMode.OFF and category == CATEGORY_COOLING and zone.at_home:
            return HVACAction.COOLING
        return HVACAction.IDLE

    # ------------------------------------------------------------------
    # Preset mode
    # ------------------------------------------------------------------

    @property
    def preset_mode(self) -> str | None:
        """Return current preset derived from zone.mode.

        zone.mode     → preset value
        auto          → 'schedule'
        party         → 'boost' (Party mode - uses HA standard for icon)
        holiday       → 'away' (Holiday mode - uses HA standard for icon)
        off + holidayActive → 'away' (vacation shows as mode=off internally)
        off / manual  → None
        """
        if self._optimistic_preset_mode is not _SENTINEL_PRESET:
            return self._optimistic_preset_mode
        zone = self._zone
        if not zone:
            return None
        # Holiday mode shows as mode=off with holidayActive=true
        if zone.holiday_active:
            return PRESET_AWAY
        return _MODE_TO_PRESET.get(zone.mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode.

        schedule → set_auto()   (follow schedule)
        boost    → set_party()  (party mode for 2 hours)
        away     → set_holiday() (vacation mode for 30 days)
        
        Note: When switching from holiday to party, we must first
        deactivate holiday mode by calling set_auto().
        """
        _LOGGER.info("Setting preset mode to: %s for zone %s", preset_mode, self._zone_id)

        # Optimistic: update UI immediately
        self._optimistic_preset_mode = preset_mode
        self._optimistic_hvac_mode = HVACMode.AUTO
        self.async_write_ha_state()

        client = self.coordinator.client
        zone = self._zone
        
        # If currently in holiday mode and switching to party, first deactivate holiday
        if zone and zone.holiday_active and preset_mode == PRESET_BOOST:
            _LOGGER.info("Deactivating holiday mode before setting party mode")
            await client.set_auto()
            # Small delay to let the API process
            import asyncio
            await asyncio.sleep(0.5)
        
        success = False
        if preset_mode == PRESET_HOME:
            success = await client.set_auto()
        elif preset_mode == PRESET_BOOST:
            success = await client.set_party()  # Apply to all zones
        elif preset_mode == PRESET_AWAY:
            success = await client.set_holiday()
        _LOGGER.info("Preset mode %s result: %s", preset_mode, success)
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Temperatures
    # ------------------------------------------------------------------

    @property
    def current_temperature(self) -> float | None:
        zone = self._zone
        return zone.temperature if zone else None

    @property
    def target_temperature(self) -> float | None:
        """In AUTO mode shows effective_setpoint (read-only).
        In HEAT/COOL mode shows manual setpoint.
        """
        if self._optimistic_target_temp is not None:
            return self._optimistic_target_temp
        zone = self._zone
        return zone.effective_setpoint if zone else None

    @property
    def min_temp(self) -> float:
        data = self.coordinator.data
        if not data:
            return 5.0
        return min(data.limits.absent_min_temp, data.manual_limits.min_temp)

    @property
    def max_temp(self) -> float:
        data = self.coordinator.data
        if not data:
            return 30.0
        return max(data.limits.absent_max_temp, data.manual_limits.max_temp)

    @property
    def target_temperature_step(self) -> float:
        data = self.coordinator.data
        return data.manual_limits.step_value if data else 0.5

    # ------------------------------------------------------------------
    # Setters
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (optimistic)."""
        # Optimistic: update UI immediately
        self._optimistic_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.AUTO:
            self._optimistic_preset_mode = PRESET_HOME
        else:
            self._optimistic_preset_mode = None
        self.async_write_ha_state()

        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await client.set_off()
        elif hvac_mode == HVACMode.AUTO:
            await client.set_auto()
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await client.set_heat_cool()
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set temperature.
        
        In AUTO mode:
          - If at_home=false (idle/away): adjusts the 'absent' setpoint
          - If at_home=true: adjusts the 'present' setpoint
        In HEAT/COOL mode: sets manual temperature directly.
        """
        zone = self._zone
        if not zone:
            return
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        # Optimistic: update UI immediately
        self._optimistic_target_temp = temperature
        self.async_write_ha_state()

        client = self.coordinator.client
        data = self.coordinator.data
        
        if self.hvac_mode == HVACMode.AUTO:
            # In AUTO mode, adjust absent or present setpoint based on at_home status
            if zone.at_home:
                # User is home → adjust present setpoint
                if data:
                    limits = data.limits
                    if not (limits.present_min_temp <= temperature <= limits.present_max_temp):
                        temperature = max(limits.present_min_temp, min(temperature, limits.present_max_temp))
                await client.set_present_absent_temperature(
                    self._zone_id, present_temperature=temperature
                )
                _LOGGER.info(
                    "Zone %s: present setpoint set to %.1f°C",
                    self._zone_id, temperature
                )
            else:
                # User is away (idle) → adjust absent setpoint
                if data:
                    limits = data.limits
                    if not (limits.absent_min_temp <= temperature <= limits.absent_max_temp):
                        temperature = max(limits.absent_min_temp, min(temperature, limits.absent_max_temp))
                await client.set_present_absent_temperature(
                    self._zone_id, absent_temperature=temperature
                )
                _LOGGER.info(
                    "Zone %s: absent setpoint set to %.1f°C",
                    self._zone_id, temperature
                )
        else:
            # HEAT/COOL mode → manual temperature
            if data:
                limits = data.limits
                if not (limits.present_min_temp <= temperature <= limits.present_max_temp):
                    temperature = max(limits.present_min_temp, min(temperature, limits.present_max_temp))
            await client.set_manual_temperature(self._zone_id, temperature)
        
        await self.coordinator.async_request_refresh()

    # ------------------------------------------------------------------
    # Extra state attributes
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict | None:
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
        if zone.calendar:
            attrs["schedule"] = [
                {"day": s.day, "bands": [b.to_dict() for b in s.bands]}
                for s in zone.calendar.schedule
            ]
        return attrs
