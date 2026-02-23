"""Text entities exposing per-day schedule bands for the Moneta Thermostat.

7 entities are created (MON–SUN). Each entity's value is a compact JSON array
of Band objects for that day, e.g.:

    [{"id":1,"setpointType":"present","start":{"hour":7,"min":0},"end":{"hour":22,"min":30}}]

An empty array [] means no active bands for that day (all-day absent).

On write:
  1. Parse the new bands JSON for the changed day.
  2. Read the current full 7-day schedule from the first zone with a calendar.
  3. Replace only the changed day's bands.
  4. Push the updated full 7-day schedule to ALL zones via set_schedule_by_zone_id().
"""
from __future__ import annotations

import json
import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MonetaThermostatCoordinator
from .models import Calendar

_LOGGER = logging.getLogger(__name__)

DAYS_OF_WEEK = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# Large enough for several bands per day; HA default is 100, we need more.
_MAX_JSON_LEN = 2000


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up schedule text entities from a config entry."""
    coordinator: MonetaThermostatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [MonetaScheduleDayText(coordinator, entry.entry_id, day) for day in DAYS_OF_WEEK]
    )


class MonetaScheduleDayText(
    CoordinatorEntity[MonetaThermostatCoordinator], TextEntity
):
    """Text entity for the bands of one day of the weekly schedule.

    Reading: returns the current bands for this day from the coordinator data
    (first zone with a calendar is used as canonical source).

    Writing: parses the new JSON, rebuilds the full 7-day schedule, and
    pushes it to every zone.
    """

    _attr_has_entity_name = True
    _attr_native_min = 2      # minimum valid value is "[]"
    _attr_native_max = _MAX_JSON_LEN

    def __init__(
        self,
        coordinator: MonetaThermostatCoordinator,
        entry_id: str,
        day: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._day = day
        self._attr_unique_id = f"{entry_id}_schedule_day_{day.lower()}"
        self._attr_name = f"Schedule {day}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Moneta Thermostat",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def _get_calendar(self) -> Calendar | None:
        """Return the calendar from the first zone that has one."""
        data = self.coordinator.data
        if not data:
            return None
        for zone in data.zones:
            if zone.calendar and zone.calendar.schedule:
                return zone.calendar
        return None

    @property
    def native_value(self) -> str:
        """Return the bands for this day as a compact JSON string."""
        calendar = self._get_calendar()
        if not calendar:
            return "[]"
        day_sched = next((s for s in calendar.schedule if s.day == self._day), None)
        if not day_sched:
            return "[]"
        return json.dumps([b.to_dict() for b in day_sched.bands], separators=(",", ":"))

    async def async_set_value(self, value: str) -> None:
        """Parse new bands JSON, rebuild full 7-day schedule, push to all zones."""
        # --- 1. Validate input ---
        try:
            new_bands: list[dict] = json.loads(value)
            if not isinstance(new_bands, list):
                raise ValueError("Expected a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            _LOGGER.error(
                "Invalid bands JSON for day %s: %s — input: %r",
                self._day, exc, value,
            )
            return

        data = self.coordinator.data
        if not data or not data.zones:
            _LOGGER.error("No thermostat data available, cannot update schedule")
            return

        # --- 2. Build current schedule map from canonical zone ---
        calendar = self._get_calendar()
        current_by_day: dict[str, list[dict]] = {d: [] for d in DAYS_OF_WEEK}
        if calendar:
            for s in calendar.schedule:
                if s.day in current_by_day:
                    current_by_day[s.day] = [b.to_dict() for b in s.bands]

        # --- 3. Replace this day's bands ---
        current_by_day[self._day] = new_bands

        # --- 4. Build ordered full-week schedule ---
        full_schedule = [{"day": d, "bands": current_by_day[d]} for d in DAYS_OF_WEEK]
        step = calendar.step if calendar else 30

        # --- 5. Push to every zone ---
        client = self.coordinator.client
        any_success = False
        for zone in data.zones:
            ok = await client.set_schedule_by_zone_id(
                zone_id=zone.id,
                schedule=full_schedule,
                step=step,
            )
            if ok:
                any_success = True
                _LOGGER.info("Schedule updated for zone %s day %s", zone.id, self._day)
            else:
                _LOGGER.error(
                    "Failed to update schedule for zone %s day %s", zone.id, self._day
                )

        if any_success:
            await self.coordinator.async_request_refresh()
