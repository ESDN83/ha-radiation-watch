"""Polls the station list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RadiationApiError, async_fetch_stations
from .const import DOMAIN
from .geo import Station

_LOGGER = logging.getLogger(__name__)


@dataclass
class StationData:
    stations: list[Station]
    fetched_at: datetime


class StationCoordinator(DataUpdateCoordinator[StationData]):
    """Fetches all stations within the far radius.

    A failed poll keeps the last good list, so the map does not go blank on a short outage.
    fetched_at shows how old the list is. Only the very first poll may fail hard.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, settings: dict) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=settings["scan_interval"]),
        )
        self.settings = settings

    async def _async_update_data(self) -> StationData:
        s = self.settings
        try:
            stations = await async_fetch_stations(
                async_get_clientsession(self.hass), s["latitude"], s["longitude"], s["radius_far"], s["max_age"]
            )
        except RadiationApiError as err:
            if self.data is not None:
                _LOGGER.warning("Keeping the last station list: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        if not stations and self.data is not None:
            return self.data
        return StationData(stations=stations, fetched_at=datetime.now(timezone.utc))
