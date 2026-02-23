"""Async API client for the Moneta Thermostat (PlanetSmartCity cloud).

This module mirrors the business logic in thermostat.api-provider.ts from
the Homebridge plugin, translated to Python/aiohttp.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp

from .const import (
    API_BASE_URL,
    API_ENDPOINT,
    API_SOURCE_HEADER,
    API_TIMEZONE_OFFSET,
    CATEGORY_HEATING,
    CATEGORY_COOLING,
    DEFAULT_ZONE_ID,
    MIN_POLLING_INTERVAL,
    SETPOINT_ABSENT,
    SETPOINT_EFFECTIVE,
    SETPOINT_PRESENT,
    REQUEST_TYPE_FULL,
    REQUEST_TYPE_SETPOINT,
)
from .models import ThermostatModel, Zone, Setpoint, SetPointType, ZoneMode, Category

_LOGGER = logging.getLogger(__name__)


class MonetaApiClient:
    """Async client for the PlanetSmartCity thermostat API.

    Mirrors the ThermostatProvider class from thermostat.api-provider.ts.
    """

    def __init__(
        self,
        access_token: str,
        session: aiohttp.ClientSession,
        polling_interval_minutes: int = 10,
    ) -> None:
        self._access_token = access_token
        self._session = session
        self._polling_interval = max(polling_interval_minutes, MIN_POLLING_INTERVAL)

        # Internal cache – mirrors this.store in the TS code
        self._cached_data: ThermostatModel | None = None
        self._expiration: datetime | None = None
        self._pending: bool = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "x-planet-source": API_SOURCE_HEADER,
            "timezone-offset": API_TIMEZONE_OFFSET,
            "Content-Type": "application/json",
        }

    def _invalidate_cache(self) -> None:
        """Invalidate the cache so the next poll fetches fresh data.

        Mirrors asyncRefreshState() in thermostat.api-provider.ts.
        """
        self._expiration = None
        _LOGGER.debug("Cache invalidated")

    async def _api_post(self, payload: dict) -> list[dict] | None:
        """POST to sensors_data_request and return the JSON response body."""
        url = f"{API_BASE_URL}{API_ENDPOINT}"
        _LOGGER.debug("Thermostat API REQUEST: %s", payload)
        try:
            async with self._session.post(
                url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error("API returned status %s", resp.status)
                    return None
                data: list[dict] = await resp.json(content_type=None)
                _LOGGER.debug("Thermostat API RESPONSE: %s", data)
                if data is None or (isinstance(data, list) and len(data) > 0 and data[0].get("error")):
                    _LOGGER.error("API error: %s", data)
                    return None
                return data
        except aiohttp.ClientError as err:
            _LOGGER.error("Error calling thermostat API: %s", err)
            return None

    async def _set_request(self, payload: dict) -> bool:
        """Send a SET request and invalidate the cache on success.

        Mirrors the pattern in thermostatApi() for non-Full request types.
        """
        _LOGGER.info("API SET request: %s", payload)
        result = await self._api_post(payload)
        if result is not None:
            # Check if API returned success
            if isinstance(result, list) and len(result) > 0:
                first_result = result[0]
                success = first_result.get("success", False)
                error = first_result.get("error", "")
                _LOGGER.info("API SET response - success: %s, error: %s", success, error)
                if not success and error:
                    _LOGGER.error("API SET failed: %s", error)
                    return False
            self._invalidate_cache()
            return True
        _LOGGER.error("API SET request returned None")
        return False

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    async def get_state(self) -> ThermostatModel | None:
        """Fetch full state from the API (with cache).

        Mirrors getState() in thermostat.api-provider.ts.
        Cache expires after polling_interval minutes (min 10).
        """
        now = datetime.now()
        if self._pending or (self._expiration and now < self._expiration):
            return self._cached_data

        self._pending = True
        try:
            _LOGGER.info("Fetching thermostat state…")
            payload = {"request_type": REQUEST_TYPE_FULL}
            data = await self._api_post(payload)
            if data:
                # The API returns a list; first element is the thermostat model
                raw = data[0] if isinstance(data, list) else data
                self._cached_data = ThermostatModel.from_dict(raw)
                self._expiration = now + timedelta(minutes=self._polling_interval)
                _LOGGER.info(
                    "Thermostat state fetched. Cached until %s",
                    self._expiration.strftime("%H:%M:%S"),
                )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Unexpected error fetching thermostat state: %s", err)
        finally:
            self._pending = False

        return self._cached_data

    def get_zone_by_id(self, zone_id: str) -> Zone | None:
        """Return a zone by its ID from the cached state."""
        if not self._cached_data:
            return None
        return next((z for z in self._cached_data.zones if z.id == zone_id), None)

    def get_setpoint_temperature(self, zone: Zone, setpoint_type: str) -> float | None:
        """Return the temperature for a given setpoint type in a zone.

        Mirrors getSetPointTemperatureByZone() in thermostat.api-provider.ts.
        """
        sp = next((s for s in zone.setpoints if s.type == setpoint_type), None)
        return sp.temperature if sp else None

    def get_presence(self) -> bool:
        """Return atHome value for the default zone (zone 1).

        Mirrors getThermostatPresence() in thermostat.api-provider.ts.
        """
        zone = self.get_zone_by_id(DEFAULT_ZONE_ID)
        return zone.at_home if zone else False

    # ------------------------------------------------------------------
    # Public write API (mirrors set* methods in thermostat.api-provider.ts)
    # ------------------------------------------------------------------

    async def set_off(self) -> bool:
        """Set all zones to OFF mode.

        Mirrors setOffTargetState() in thermostat.api-provider.ts.
        Sets mode=off, expiration=0, setpoint=effective at temp+1 for each zone.
        Sends all zones (not just zone 1) because same_mode_for_all_zones=true.
        """
        if not self._cached_data:
            return False

        zones_payload = []
        for zone in self._cached_data.zones:
            effective_temp = zone.temperature + 1
            zones_payload.append({
                "id": zone.id,
                "mode": ZoneMode.OFF,
                "expiration": 0,
                "setpoints": [
                    {"type": SETPOINT_EFFECTIVE, "temperature": effective_temp}
                ],
            })

        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_auto(self) -> bool:
        """Set all zones to AUTO mode.

        Mirrors setAutoTargetState() in thermostat.api-provider.ts.
        Sends all zones because same_mode_for_all_zones=true.
        """
        if not self._cached_data:
            return False
        zones_payload = [
            {"id": zone.id, "mode": ZoneMode.AUTO, "expiration": 0}
            for zone in self._cached_data.zones
        ]
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_heat_cool(self) -> bool:
        """Set all zones to MANUAL mode using each zone's present setpoint.

        Mirrors setHeatCoolTargetState() in thermostat.api-provider.ts.
        """
        if not self._cached_data:
            return False
        zones_payload = []
        for zone in self._cached_data.zones:
            present_temp = self.get_setpoint_temperature(zone, SETPOINT_PRESENT) or 21.0
            zones_payload.append(
                {
                    "id": zone.id,
                    "mode": ZoneMode.MANUAL,
                    "currentManualTemperature": present_temp,
                    "setpoints": [
                        {"type": SETPOINT_EFFECTIVE, "temperature": present_temp}
                    ],
                }
            )
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_party(self, zone_id: str | None = None, hours: int = 4) -> bool:
        """Set PARTY (Boost) mode for all zones or a specific zone.

        Corresponds to preset 'Boost' — thermostat raises to comfort temp
        and holds there regardless of schedule.
        
        Args:
            zone_id: Optional zone ID. If None, applies to all zones.
            hours: Duration in hours. Fixed to 4 hours due to backend limitations.
        
        Note: The Delta Control backend has known issues with Party mode duration.
        Only 4 hours (240 minutes) works reliably. Other durations are ignored
        by the thermostat which always shows 4h on the display.
        """
        if not self._cached_data:
            _LOGGER.error("set_party: No cached data available")
            return False
        
        # Fixed to 4 hours - the only duration that works reliably
        # Backend bug: other durations are accepted but thermostat shows 4h
        hours = 4
        
        now_ts = int(time.time())
        # Round to next full minute
        now_rounded = ((now_ts // 60) + 1) * 60
        
        # Calculate the next valid base timestamp where % 7200 == 2220
        # This pattern is required by the API validation
        remainder = now_rounded % 7200
        if remainder <= 2220:
            next_valid_base = now_rounded - remainder + 2220
        else:
            next_valid_base = now_rounded - remainder + 7200 + 2220
        
        # For 4 hours, use base + 7200
        expiration_ts = next_valid_base + 7200
        
        # Ensure expiration is in the future (60-540 min from now)
        minutes_from_now = (expiration_ts - now_ts) // 60
        if minutes_from_now < 60:
            expiration_ts += 7200
            minutes_from_now = (expiration_ts - now_ts) // 60
        
        _LOGGER.info(
            "set_party: 4h fixed, now=%d, expiration=%d (%%7200=%d), minutes_from_now=%d",
            now_ts, expiration_ts, expiration_ts % 7200, minutes_from_now
        )
        
        zones = (
            [z for z in self._cached_data.zones if z.id == zone_id]
            if zone_id
            else self._cached_data.zones
        )
        zones_payload = []
        for zone in zones:
            present_temp = self.get_setpoint_temperature(zone, SETPOINT_PRESENT) or 21.0
            zones_payload.append({
                "id": zone.id,
                "mode": ZoneMode.PARTY,
                "expiration": expiration_ts,
                "currentManualTemperature": present_temp,
            })
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_frost_protection(self) -> bool:
        """Set all zones to frost-protection hold (Protezione antigelo).

        Uses mode=off with the minimum absent setpoint temperature to
        prevent pipes freezing while keeping energy use minimal.
        """
        if not self._cached_data:
            return False
        zones_payload = []
        for zone in self._cached_data.zones:
            frost_temp = self.get_setpoint_temperature(zone, SETPOINT_ABSENT) or 7.0
            zones_payload.append({
                "id": zone.id,
                "mode": ZoneMode.OFF,
                "expiration": 0,
                "setpoints": [{"type": SETPOINT_EFFECTIVE, "temperature": frost_temp}],
            })
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_holiday(self, days: int = 30) -> bool:
        """Set HOLIDAY mode for all zones.

        Activates vacation/holiday mode with antifreeze protection.
        
        Args:
            days: Duration in days. Due to API limitations, only certain
                  timestamp values work. Default is 30 days using a known
                  working timestamp pattern.
        
        Note: The API behavior for holiday mode is inconsistent. We use a
        specific timestamp value (1772000000 pattern) that has been tested
        to work reliably.
        """
        if not self._cached_data:
            return False
        
        # Use a "magic" timestamp that works with the API
        # Pattern discovered: multiples ending in xx72000000 or xx70000000 work
        # We calculate the nearest working timestamp
        now = int(time.time())
        # Round up to next multiple of 2000000, then ensure it ends in pattern
        base = ((now // 2000000) + 1) * 2000000
        # Adjust to get a value that works (ending in 0 or 2 in millions place)
        expiration_ts = base
        if (base // 1000000) % 10 not in (0, 2):
            expiration_ts = base + 2000000
        
        zones_payload = []
        for zone in self._cached_data.zones:
            zones_payload.append({
                "id": zone.id,
                "mode": ZoneMode.HOLIDAY,
                "expiration": expiration_ts,
            })
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": zones_payload,
        }
        return await self._set_request(payload)

    async def set_manual_temperature(self, zone_id: str, temperature: float) -> bool:
        """Set the manual temperature for a zone.

        Mirrors setCurrentMananualTemperatureByZoneId() in thermostat.api-provider.ts.
        """
        if not self._cached_data:
            return False
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": [
                {
                    "id": zone_id,
                    "currentManualTemperature": temperature,
                    "mode": ZoneMode.MANUAL,
                }
            ],
        }
        return await self._set_request(payload)

    async def set_present_absent_temperature(
        self,
        zone_id: str,
        present_temperature: float | None = None,
        absent_temperature: float | None = None,
    ) -> bool:
        """Update present and/or absent setpoints for a zone (AUTO mode).

        Mirrors setPresentAbsentTemperatureByZoneId() in thermostat.api-provider.ts.
        Skips the API call if the value is already the same (deduplication).
        """
        if not self._cached_data:
            return False

        zone = self.get_zone_by_id(zone_id)
        if not zone:
            return False

        # Deduplication logic (same as TS plugin)
        skip_present = present_temperature is None or (
            self.get_setpoint_temperature(zone, SETPOINT_PRESENT) == present_temperature
        )
        skip_absent = absent_temperature is None or (
            self.get_setpoint_temperature(zone, SETPOINT_ABSENT) == absent_temperature
        )

        setpoints = []
        if not skip_present:
            setpoints.append({"type": SETPOINT_PRESENT, "temperature": present_temperature})
        if not skip_absent:
            setpoints.append({"type": SETPOINT_ABSENT, "temperature": absent_temperature})

        if not setpoints:
            _LOGGER.debug("set_present_absent_temperature – update not required, skipping")
            return True

        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": [{"id": zone_id, "setpoints": setpoints}],
        }
        return await self._set_request(payload)

    async def set_schedule_by_zone_id(
        self,
        zone_id: str,
        schedule: list[dict],
        step: int = 30,
    ) -> bool:
        """Update the weekly schedule calendar for a zone.

        The schedule is a list of dicts with this structure:
          {"day": "MON", "bands": [
              {"id": 1, "setpointType": "present",
               "start": {"hour": 16, "min": 0},
               "end": {"hour": 21, "min": 30}}
          ]}

        Pass an empty 'bands' list for a day with no active bands (entire day absent).
        """
        if not self._cached_data:
            return False
        payload = {
            "request_type": REQUEST_TYPE_SETPOINT,
            "unitCode": self._cached_data.unit_code,
            "category": self._cached_data.category,
            "zones": [{
                "id": zone_id,
                "calendar": {
                    "step": step,
                    "schedule": schedule,
                },
            }],
        }
        return await self._set_request(payload)

