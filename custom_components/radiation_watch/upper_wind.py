"""Wind aloft from Open-Meteo (open source, free, no key).

A plume travels with the wind at about 1 to 1.5 km height (850 hPa), rain washes it out from
higher clouds (700 hPa, about 3 km). Near the ground the wind often turns by 40 to 70 degrees
and is three to four times slower, so the surface wind alone gives wrong sectors and far too
long arrival times. Only the location rounded to 0.1 degrees (about 10 km) is sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, USER_AGENT

_LOGGER = logging.getLogger(__name__)
URL = "https://api.open-meteo.com/v1/forecast"
# Up to this age the last poll counts as current. After that the integration keeps using the saved
# forecast for the current hour (marked as forecast), until the forecast runs out.
FRESH_FOR = timedelta(hours=3)
FORECAST_HOURS = 72  # from the current hour on; forecast_days would start at midnight
STORE_VERSION = 1


@dataclass
class UpperWind:
    """Wind aloft for one hour."""

    bearing_850: float
    kmh_850: float
    bearing_700: float | None
    kmh_700: float | None
    valid_for: datetime  # hour of the forecast value used
    fetched_at: datetime  # when this forecast was loaded
    from_forecast: bool = False  # True: no fresh poll for FRESH_FOR, value from the saved forecast


@dataclass
class Forecast:
    """Hourly rows [hour ISO UTC, bearing 850, km/h 850, bearing 700, km/h 700] and when they were loaded."""

    hours: list[list]
    fetched_at: datetime


def to_rows(hourly: dict) -> list[list]:
    """Open-Meteo's parallel arrays as rows; hours without 850 hPa wind are dropped."""
    rows = []
    for i, stamp in enumerate(hourly["time"]):
        b8, k8 = hourly["wind_direction_850hPa"][i], hourly["wind_speed_850hPa"][i]
        if b8 is None or k8 is None:
            continue
        rows.append([stamp, b8, k8, hourly["wind_direction_700hPa"][i], hourly["wind_speed_700hPa"][i]])
    return rows


def wind_at(fc: Forecast | None, now: datetime) -> UpperWind | None:
    """Wind for the current hour from the forecast, None when the forecast does not cover it."""
    if fc is None:
        return None
    stamp = now.strftime("%Y-%m-%dT%H:00")
    for t, b8, k8, b7, k7 in fc.hours:
        if t == stamp:
            return UpperWind(
                float(b8), float(k8),
                float(b7) if b7 is not None else None, float(k7) if k7 is not None else None,
                now.replace(minute=0, second=0, microsecond=0), fc.fetched_at,
                from_forecast=now - fc.fetched_at > FRESH_FOR,
            )
    return None


class UpperWindCoordinator(DataUpdateCoordinator[Forecast | None]):
    """Hourly. Keeps the whole forecast, also on disk.

    The scenario this protects against: an incident takes the internet down. Then the forecast
    from the last poll is still a far better guess of the wind aloft than nothing, for up to
    three days. The engine and the card mark such values as forecast.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, lat: float, lon: float) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_upper_wind", update_interval=timedelta(minutes=60))
        self.lat, self.lon = round(lat, 1), round(lon, 1)
        self._store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.upper_wind")

    async def async_load_saved(self) -> None:
        try:
            saved = await self._store.async_load()
            if saved and saved.get("location") == [self.lat, self.lon]:
                self.data = Forecast(hours=saved["hours"], fetched_at=datetime.fromisoformat(saved["fetched_at"]))
        except Exception as err:  # noqa: BLE001 - a broken file only means: no saved forecast
            _LOGGER.warning("Saved wind forecast not usable: %s", err)

    async def _async_update_data(self) -> Forecast | None:
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "hourly": "wind_direction_850hPa,wind_speed_850hPa,wind_direction_700hPa,wind_speed_700hPa",
            "forecast_hours": FORECAST_HOURS,
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        }
        try:
            async with async_get_clientsession(self.hass).get(
                URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
            rows = to_rows(data["hourly"])
            if not rows:
                raise ValueError("no 850 hPa wind")
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as err:
            _LOGGER.warning("Upper wind from Open-Meteo not available, using the saved forecast: %s", err)
            return self.data
        fc = Forecast(hours=rows, fetched_at=datetime.now(timezone.utc))
        await self._store.async_save({"location": [self.lat, self.lon], "fetched_at": fc.fetched_at.isoformat(), "hours": rows})
        return fc

    def current(self) -> UpperWind | None:
        return wind_at(self.data, datetime.now(timezone.utc))
