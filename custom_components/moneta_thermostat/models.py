"""Data models for the Moneta Thermostat integration.

These dataclasses mirror the TypeScript interfaces and enums in
thermostat.model.ts from the Homebridge plugin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums (plain string constants – easier to map from JSON)
# ---------------------------------------------------------------------------


class ZoneMode:
    AUTO = "auto"
    OFF = "off"
    MANUAL = "manual"
    PARTY = "party"
    HOLIDAY = "holiday"


class Category:
    HEATING = "heating"
    COOLING = "cooling"
    OFF = "off"


class SeasonName:
    WINTER = "winter"
    SUMMER = "summer"


class SetPointType:
    ABSENT = "absent"
    PRESENT = "present"
    EFFECTIVE = "effective"


class RequestType:
    FULL = "full_bo"
    SETPOINT = "post_bo_setpoint"


# ---------------------------------------------------------------------------
# Dataclasses (mirrors TypeScript interfaces)
# ---------------------------------------------------------------------------


@dataclass
class Setpoint:
    type: str
    temperature: float

    @classmethod
    def from_dict(cls, data: dict) -> "Setpoint":
        return cls(
            type=data.get("type", ""),
            temperature=data.get("temperature", 0.0),
        )


@dataclass
class Limits:
    steps: int = 0
    step_value: float = 0.5
    present_max_temp: float = 30.0
    present_min_temp: float = 5.0
    absent_max_temp: float = 30.0
    absent_min_temp: float = 5.0
    present_is_unique: bool = False
    absent_is_unique: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Limits":
        if not data:
            return cls()
        return cls(
            steps=data.get("steps", 0),
            step_value=data.get("step_value", 0.5),
            present_max_temp=data.get("present_max_temp", 30.0),
            present_min_temp=data.get("present_min_temp", 5.0),
            absent_max_temp=data.get("absent_max_temp", 30.0),
            absent_min_temp=data.get("absent_min_temp", 5.0),
            present_is_unique=data.get("present_is_unique", False),
            absent_is_unique=data.get("absent_is_unique", False),
        )


@dataclass
class ManualLimits:
    min_temp: float = 5.0
    max_temp: float = 30.0
    steps: int = 0
    step_value: float = 0.5

    @classmethod
    def from_dict(cls, data: dict) -> "ManualLimits":
        if not data:
            return cls()
        return cls(
            min_temp=data.get("min_temp", 5.0),
            max_temp=data.get("max_temp", 30.0),
            steps=data.get("steps", 0),
            step_value=data.get("step_value", 0.5),
        )


@dataclass
class Zone:
    id: str
    temperature: float
    humidity: Any
    at_home: bool
    at_home_for_scheduler: bool
    block_humidity: bool
    effective_setpoint: float
    setpoints: list[Setpoint] = field(default_factory=list)
    mode: str = ZoneMode.AUTO
    setpoint_selected: str = SetPointType.PRESENT
    expiration: Any = None
    current_manual_temperature: float = 0.0
    date_expiration: Any = None

    @classmethod
    def from_dict(cls, data: dict) -> "Zone":
        return cls(
            id=str(data.get("id", "")),
            temperature=data.get("temperature", 0.0),
            humidity=data.get("humidity"),
            at_home=bool(data.get("atHome", False)),
            at_home_for_scheduler=bool(data.get("atHomeForScheduler", False)),
            block_humidity=bool(data.get("blockHumidity", False)),
            effective_setpoint=data.get("effectiveSetpoint", 0.0),
            setpoints=[Setpoint.from_dict(s) for s in data.get("setpoints", [])],
            mode=data.get("mode", ZoneMode.AUTO),
            setpoint_selected=data.get("setpointSelected", SetPointType.PRESENT),
            expiration=data.get("expiration"),
            current_manual_temperature=data.get("currentManualTemperature", 0.0),
            date_expiration=data.get("dateExpiration"),
        )


@dataclass
class Season:
    id: str
    limits: Any = None

    @classmethod
    def from_dict(cls, data: dict) -> "Season":
        if not data:
            return cls(id=SeasonName.WINTER)
        return cls(id=data.get("id", SeasonName.WINTER), limits=data.get("limits"))


@dataclass
class ThermostatModel:
    provider: str
    unit_code: str
    measure_unit: str
    external_temperature: float
    category: str
    season: Season
    zones: list[Zone] = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    manual_limits: ManualLimits = field(default_factory=ManualLimits)

    @classmethod
    def from_dict(cls, data: dict) -> "ThermostatModel":
        return cls(
            provider=data.get("provider", ""),
            unit_code=data.get("unitCode", ""),
            measure_unit=data.get("measureUnit", "C"),
            external_temperature=data.get("externalTemperature", 0.0),
            category=data.get("category", Category.OFF),
            season=Season.from_dict(data.get("season", {})),
            zones=[Zone.from_dict(z) for z in data.get("zones", [])],
            limits=Limits.from_dict(data.get("limits", {})),
            manual_limits=ManualLimits.from_dict(data.get("manual_limits", {})),
        )
