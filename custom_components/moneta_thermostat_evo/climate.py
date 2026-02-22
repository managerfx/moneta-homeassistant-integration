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
    PRESET_ECO,
    PRESET_NONE,
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
from .models import Zone, ZoneMode

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Preset constants
# ---------------------------------------------------------------------------
PRESET_SCHEDULE = "Pianificazione"   # mode=auto  — follows weekly schedule
PRESET_FUORI_CASA = "Fuori casa"     # mode=auto  — away (reads from atHome state)
PRESET_BOOST = "Boost"               # mode=party — full comfort temp
PRESET_FROST = "Protezione antigelo" # mode=off   — frost/minimum temp

ALL_PRESETS = [PRESET_SCHEDULE, PRESET_FUORI_CASA, PRESET_BOOST, PRESET_FROST]

# Maps zone.mode → preset label
_MODE_TO_PRESET = {
    ZONE_MODE_AUTO: PRESET_SCHEDULE,
    ZONE_MODE_PARTY: PRESET_BOOST,
    ZONE_MODE_HOLIDAY: PRESET_FUORI_CASA,
    ZONE_MODE_OFF: PRESET_FROST,
    ZONE_MODE_MANUAL: None,  # In manual there's no preset
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

    Presets (available when hvac_mode = AUTO):
        Pianificazione       → follows the weekly schedule calendar
        Fuori casa           → away mode (atHome=false on physical device)
        Boost                → party/boost mode (max comfort)
        Protezione antigelo  → frost protection (zone in minimum-temp hold)

    Present/absent setpoints are managed via number.py entities.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
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
        zone = self._zone
        if not zone:
            return None
        # OFF or MANUAL → direct mapping
        if zone.mode == ZONE_MODE_OFF:
            return HVACMode.OFF
        if zone.mode == ZONE_MODE_MANUAL:
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
        if zone.mode != ZONE_MODE_OFF and category == CATEGORY_HEATING and zone.at_home:
            return HVACAction.HEATING
        if zone.mode != ZONE_MODE_OFF and category == CATEGORY_COOLING and zone.at_home:
            return HVACAction.COOLING
        return HVACAction.IDLE

    # ------------------------------------------------------------------
    # Preset mode
    # ------------------------------------------------------------------

    @property
    def preset_mode(self) -> str | None:
        """Return current preset derived from zone.mode.

        Mapping:
            auto    → Pianificazione   (following schedule)
            party   → Boost
            holiday → Fuori casa       (holiday away mode — set by physical device)
            off     → Protezione antigelo
            manual  → None             (no preset in manual mode)
        """
        zone = self._zone
        if not zone:
            return None
        # atHome=false + mode=auto → away (physical button was pressed)
        if zone.mode == ZONE_MODE_AUTO and not zone.at_home:
            return PRESET_FUORI_CASA
        return _MODE_TO_PRESET.get(zone.mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode.

        Pianificazione  → set_auto()   (follow schedule)
        Fuori casa      → set_auto()   (away — we can't force atHome via API,
                                        but user should press physical button;
                                        this resets any manual override to auto)
        Boost           → set_party()
        Protezione antigelo → set_frost()
        """
        client = self.coordinator.client
        if preset_mode == PRESET_SCHEDULE:
            await client.set_auto()
        elif preset_mode == PRESET_FUORI_CASA:
            # Best-effort: return to auto. Physical device controls atHome flag.
            await client.set_auto()
        elif preset_mode == PRESET_BOOST:
            await client.set_party(self._zone_id)
        elif preset_mode == PRESET_FROST:
            await client.set_frost_protection()
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
        """Set manual temperature (only in HEAT/COOL mode)."""
        zone = self._zone
        if not zone:
            return
        if self.hvac_mode == HVACMode.AUTO:
            _LOGGER.warning(
                "Zone %s: set temperature ignored in AUTO mode. "
                "Use Pianificazione schedule or switch to HEAT/COOL mode.",
                self._zone_id,
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
