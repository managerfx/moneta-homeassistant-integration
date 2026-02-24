"""DataUpdateCoordinator for the Moneta Thermostat integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MonetaApiClient
from .const import DOMAIN
from .models import ThermostatModel

if TYPE_CHECKING:
    from .climate import MonetaClimateEntity
    from .number import MonetaSetpointNumber

_LOGGER = logging.getLogger(__name__)


class MonetaThermostatCoordinator(DataUpdateCoordinator[ThermostatModel | None]):
    """Coordinator that polls the Moneta API and distributes data to entities.

    Also keeps a lightweight registry of climate / number entities so that
    optimistic updates can be propagated to *all* sibling zones when the
    backend command is global (mode, preset, absent temperature).
    """

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

        # Entity registries – populated by entities in their __init__
        self.climate_entities: list[MonetaClimateEntity] = []
        self.number_entities: list[MonetaSetpointNumber] = []

    async def _async_update_data(self) -> ThermostatModel | None:
        """Fetch the full thermostat state from the API."""
        data = await self.client.get_state()
        if data is None:
            raise UpdateFailed("Failed to fetch thermostat state from Moneta API")
        return data
