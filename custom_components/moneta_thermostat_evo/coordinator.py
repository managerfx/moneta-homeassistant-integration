"""DataUpdateCoordinator for the Moneta Thermostat integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MonetaApiClient
from .const import DOMAIN
from .models import ThermostatModel

_LOGGER = logging.getLogger(__name__)


class MonetaThermostatCoordinator(DataUpdateCoordinator[ThermostatModel | None]):
    """Coordinator that polls the Moneta API and distributes data to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MonetaApiClient,
        polling_interval_minutes: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=polling_interval_minutes),
        )
        self.client = client

    async def _async_update_data(self) -> ThermostatModel | None:
        """Fetch the full thermostat state from the API."""
        data = await self.client.get_state()
        if data is None:
            raise UpdateFailed("Failed to fetch thermostat state from Moneta API")
        return data
