"""Polls the station list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import async_fetch_stations
from .const import DOMAIN
from .geo import Station

_LOGGER = logging.getLogger(__name__)


STORE_VERSION = 1


STORE_VERSION = 1


@dataclass
class StationData:
    sources: dict[str, list[Station]]  # per data source, see api.SOURCE_*
    fetched_at: datetime | None  # last poll where any source answered; None: never

    @property
    def stations(self) -> list[Station]:
        return [x for lst in self.sources.values() for x in lst]


def _row(x: Station) -> list:
    return [x.name, x.latitude, x.longitude, x.value, x.country, x.measured]


class StationCoordinator(DataUpdateCoordinator[StationData]):
    """Fetches all stations within the far radius.

    Each source keeps its last good list when it fails, so an outage of one source (on
    15./16.10.2026 the BfS database failed for EURDEP longer than for the German network)
    does not wipe its stations from the map. Their measuring time stays, so the warning
    engine greys them out once they are older than max_age. The lists are also saved to
    disk: after a restart during an outage the map shows the saved stations instead of
    nothing. A poll never fails hard, without any data the engine reports "no current data".
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
        self._store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.stations")

    async def async_load_saved(self) -> None:
        """Start with the lists saved by the last good poll, or empty ones."""
        saved = None
        try:
            saved = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - a broken file only means: no saved list
            _LOGGER.warning("Saved station list not readable: %s", err)
        data = StationData(sources={}, fetched_at=None)
        if saved:
            try:
                data = StationData(
                    sources={k: [Station(*row) for row in rows] for k, rows in saved["sources"].items()},
                    fetched_at=datetime.fromisoformat(saved["fetched_at"]),
                )
            except (KeyError, TypeError, ValueError, AttributeError) as err:
                _LOGGER.warning("Saved station list not usable: %s", err)
        self.data = data

    async def _async_update_data(self) -> StationData:
        s = self.settings
        fetched = await async_fetch_stations(
            async_get_clientsession(self.hass), s["latitude"], s["longitude"], s["radius_far"], s["max_age"]
        )
        answered = {k: v for k, v in fetched.items() if v is not None}
        if not answered:
            _LOGGER.warning("Keeping the last station list: no data source reachable")
            return self.data
        if not any(answered.values()) and self.data.stations:
            # Every source answered, but nothing at all: rather a service glitch than reality.
            return self.data
        sources = {**self.data.sources, **answered}
        data = StationData(sources=sources, fetched_at=datetime.now(timezone.utc))
        await self._store.async_save(
            {"fetched_at": data.fetched_at.isoformat(), "sources": {k: [_row(x) for x in v] for k, v in sources.items()}}
        )
        return data
