"""Async API client for the Moneta Thermostat (PlanetSmartCity cloud).

This module mirrors the business logic in thermostat.api-provider.ts from
the Homebridge plugin, translated to Python/aiohttp.
"""
from __future__ import annotations

import logging
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
                if not data or (isinstance(data, list) and data[0].get("error")):
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
        result = await self._api_post(payload)
        if result is not None:
            self._invalidate_cache()
            return True
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

    async def set_party(self, zone_id: str | None = None) -> bool:
        """Set PARTY (Boost) mode for all zones or a specific zone.

        Corresponds to preset 'Boost' — thermostat raises to comfort temp
        and holds there regardless of schedule.
        """
        if not self._cached_data:
            return False
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
                "currentManualTemperature": present_temp,
                "setpoints": [{"type": SETPOINT_EFFECTIVE, "temperature": present_temp}],
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

