"""Constants for the Moneta Thermostat integration."""
from __future__ import annotations

DOMAIN = "moneta_thermostat"
MANUFACTURER = "Delta Controls"
MODEL = "eZNT-T100"

# API
API_BASE_URL = "https://portal.planetsmartcity.com/api/v3/"
API_ENDPOINT = "sensors_data_request"
API_SOURCE_HEADER = "mobile"
API_TIMEZONE_OFFSET = "-60"

# Request types (mirrors RequestType enum in thermostat.model.ts)
REQUEST_TYPE_FULL = "full_bo"
REQUEST_TYPE_SETPOINT = "post_bo_setpoint"

# Zone modes (mirrors ZoneMode enum)
ZONE_MODE_AUTO = "auto"
ZONE_MODE_OFF = "off"
ZONE_MODE_MANUAL = "manual"
ZONE_MODE_PARTY = "party"
ZONE_MODE_HOLIDAY = "holiday"

# Category (mirrors Category enum)
CATEGORY_HEATING = "heating"
CATEGORY_COOLING = "cooling"
CATEGORY_OFF = "off"

# Season (mirrors SeasonName enum)
SEASON_WINTER = "winter"
SEASON_SUMMER = "summer"

# Setpoint types (mirrors SetPointType enum)
SETPOINT_ABSENT = "absent"
SETPOINT_PRESENT = "present"
SETPOINT_EFFECTIVE = "effective"

# Config keys
CONF_ACCESS_TOKEN = "access_token"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_ZONES_NAMES = "zones_names"

# Defaults
DEFAULT_POLLING_INTERVAL = 10  # minutes
MIN_POLLING_INTERVAL = 5       # minutes
DEFAULT_ZONE_ID = "1"
