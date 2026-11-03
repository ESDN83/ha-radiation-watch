"""Clients for the station data: BfS WFS (German ODL network) and optionally FANC TELERAD (Belgium)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import math
import re

import aiohttp

from .const import LAYER_ODL_DE, TELERAD_URL, USER_AGENT, WFS_URL
from .geo import KM_PER_DEG_LAT, Station, distance_bearing, parse_telerad

_LOGGER = logging.getLogger(__name__)


def parse_body(text: str) -> dict:
    """GeoJSON from the service. On a server fault GeoServer answers 200 with an XML
    ExceptionReport instead; its first line goes into the error instead of a JSON parse error."""
    if text.lstrip().startswith("<"):
        m = re.search(r"<ows:ExceptionText>\s*([^\n<]*)", text)
        raise ValueError(f"service error: {m.group(1).strip() if m else 'no GeoJSON in the answer'}")
    return json.loads(text)


def _bbox(lat: float, lon: float, radius_km: float) -> str:
    """lat/lon box around home, axis order lat,lon as GeoServer expects for EPSG:4326."""
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = radius_km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    return f"{lat - dlat:.4f},{lon - dlon:.4f},{lat + dlat:.4f},{lon + dlon:.4f}"


def _params(layer: str, cql: str) -> dict[str, str]:
    return {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "typeName": layer,
        "propertyName": "name,value,end_measure,geom",
        "CQL_FILTER": cql,
    }


def parse_features(
    features: list[dict], lat: float, lon: float, radius_km: float, max_age_h: float, now: datetime
) -> list[Station]:
    """Turn GeoJSON features into stations: inside the radius, with a value, not older than max_age_h."""
    oldest = now - timedelta(hours=max_age_h)
    out: list[Station] = []
    for f in features:
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        value = props.get("value")
        if len(coords) < 2 or not isinstance(value, (int, float)):
            continue
        s_lon, s_lat = float(coords[0]), float(coords[1])
        if distance_bearing(lat, lon, s_lat, s_lon)[0] > radius_km:
            continue
        try:
            measured = datetime.fromisoformat(str(props.get("end_measure")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if measured < oldest:
            continue
        name = str(props.get("name") or "?")
        if name.isupper():
            name = name.title()
        out.append(
            Station(name=name, latitude=s_lat, longitude=s_lon, value=float(value), country="DE", measured=measured.timestamp())
        )
    return out


SOURCE_ODL_DE = "odl_de"
SOURCE_TELERAD = "telerad"


def active_sources(use_telerad: bool) -> list[str]:
    return [SOURCE_ODL_DE, SOURCE_TELERAD] if use_telerad else [SOURCE_ODL_DE]


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict[str, str]) -> dict:
    async with session.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=45)
    ) as resp:
        resp.raise_for_status()
        return parse_body(await resp.text())


async def _fetch_odl_de(session: aiohttp.ClientSession, lat: float, lon: float, radius_km: float, max_age_h: float) -> list[Station]:
    cql = f"site_status=1 AND BBOX(geom,{_bbox(lat, lon, radius_km)})"
    data = await _get_json(session, WFS_URL, _params(LAYER_ODL_DE, cql))
    return parse_features(data.get("features") or [], lat, lon, radius_km, max_age_h, datetime.now(timezone.utc))


async def _fetch_telerad(session: aiohttp.ClientSession, lat: float, lon: float, radius_km: float, max_age_h: float) -> list[Station]:
    params = {
        "where": "StationType='L'",
        "outFields": "Name,Location,Lat,Lon,InServiceNL,Unite,Station_Value,StationType,Date_Time",
        "returnGeometry": "false",
        "resultRecordCount": "2000",
        "f": "json",
    }
    data = await _get_json(session, TELERAD_URL, params)
    if "error" in data:  # ArcGIS reports errors with HTTP 200
        raise ValueError(f"service error: {data['error'].get('message')}")
    return parse_telerad(data.get("features") or [], lat, lon, radius_km, max_age_h, datetime.now(timezone.utc).timestamp())


async def async_fetch_stations(
    session: aiohttp.ClientSession, lat: float, lon: float, radius_km: float, max_age_h: float, use_telerad: bool = False
) -> dict[str, list[Station] | None]:
    """Per active source the stations, or None when that source failed."""
    fetchers = {SOURCE_ODL_DE: _fetch_odl_de, SOURCE_TELERAD: _fetch_telerad}
    result: dict[str, list[Station] | None] = {}
    for key in active_sources(use_telerad):
        try:
            result[key] = await fetchers[key](session, lat, lon, radius_km, max_age_h)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning("Fetching %s failed: %s", key, err)
            result[key] = None
    return result
