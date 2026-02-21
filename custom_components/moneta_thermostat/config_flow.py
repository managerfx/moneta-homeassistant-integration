"""Config flow for the Moneta Thermostat integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MonetaApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_POLLING_INTERVAL,
    CONF_ZONES_NAMES,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    MIN_POLLING_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_POLLING_INTERVAL, default=DEFAULT_POLLING_INTERVAL): vol.All(
            int, vol.Range(min=MIN_POLLING_INTERVAL)
        ),
    }
)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input by attempting a real API call."""
    session = async_get_clientsession(hass)
    client = MonetaApiClient(
        access_token=data[CONF_ACCESS_TOKEN],
        session=session,
        polling_interval_minutes=data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
    )
    state = await client.get_state()
    if state is None:
        raise ValueError("cannot_connect")
    return {"title": f"Moneta Thermostat ({state.unit_code})"}


class MonetaThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Moneta Thermostat."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during config flow validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
