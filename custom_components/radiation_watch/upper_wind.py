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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, USER_AGENT

_LOGGER = logging.getLogger(__name__)
URL = "https://api.open-meteo.com/v1/forecast"
STALE_AFTER = timedelta(hours=3)  # older than this: not used, the warning falls back to the surface wind


@dataclass
class UpperWind:
    bearing_850: float
    kmh_850: float
    bearing_700: float | None
    kmh_700: float | None
    valid_for: datetime  # hour of the forecast value used
    fetched_at: datetime


def pick_hour(hourly: dict, now: datetime) -> int | None:
    """Index of the current hour in Open-Meteo's hourly arrays (times in UTC)."""
    stamp = now.strftime("%Y-%m-%dT%H:00")
    times = hourly.get("time") or []
    return times.index(stamp) if stamp in times else None


class UpperWindCoordinator(DataUpdateCoordinator[UpperWind | None]):
    """Hourly. A failed poll keeps the last value; it is ignored once older than STALE_AFTER."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, lat: float, lon: float) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_upper_wind", update_interval=timedelta(minutes=60))
        self.lat, self.lon = round(lat, 1), round(lon, 1)

    async def _async_update_data(self) -> UpperWind | None:
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "hourly": "wind_direction_850hPa,wind_speed_850hPa,wind_direction_700hPa,wind_speed_700hPa",
            "forecast_days": 2,
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        }
        try:
            async with async_get_clientsession(self.hass).get(
                URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
            hourly = data["hourly"]
            now = datetime.now(timezone.utc)
            i = pick_hour(hourly, now)
            if i is None:
                raise ValueError("current hour not in the forecast")
            b8, k8 = hourly["wind_direction_850hPa"][i], hourly["wind_speed_850hPa"][i]
            b7, k7 = hourly["wind_direction_700hPa"][i], hourly["wind_speed_700hPa"][i]
            if b8 is None or k8 is None:
                raise ValueError("no 850 hPa wind")
            return UpperWind(
                float(b8), float(k8),
                float(b7) if b7 is not None else None, float(k7) if k7 is not None else None,
                now.replace(minute=0, second=0, microsecond=0), now,
            )
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, IndexError) as err:
            _LOGGER.warning("Upper wind from Open-Meteo not available, using the surface wind: %s", err)
            return self.data  # keep the last value, the engine checks its age

    def current(self) -> UpperWind | None:
        d = self.data
        if d is None or datetime.now(timezone.utc) - d.fetched_at > STALE_AFTER:
            return None
        return d
