"""Client for the open BfS WFS service (German ODL network and European EURDEP data)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import math
import re

import aiohttp

from .const import LAYER_EURDEP, LAYER_ODL_DE, USER_AGENT, WFS_URL
from .geo import KM_PER_DEG_LAT, Station, distance_bearing

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
    features: list[dict], eurdep: bool, lat: float, lon: float, radius_km: float, max_age_h: float, now: datetime
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
        if eurdep:
            # Feature id looks like "eurdep_latestValue.BE55700", the country code leads the station id.
            country = str(f.get("id", "")).split(".")[-1][:2] or "EU"
        else:
            country = "DE"
        out.append(
            Station(name=name, latitude=s_lat, longitude=s_lon, value=float(value), country=country, measured=measured.timestamp())
        )
    return out


SOURCE_EURDEP = "eurdep"
SOURCE_ODL_DE = "odl_de"


async def async_fetch_stations(
    session: aiohttp.ClientSession, lat: float, lon: float, radius_km: float, max_age_h: float
) -> dict[str, list[Station] | None]:
    """Fetch both layers. Per source the stations, or None when that source failed."""
    bbox = _bbox(lat, lon, radius_km)
    # EURDEP lists each station once per analysis window (6/12/24/48/72 h) with the same value.
    sources = [
        (SOURCE_EURDEP, LAYER_EURDEP, f"analyzed_range_in_h=6 AND BBOX(geom,{bbox})", True),
        (SOURCE_ODL_DE, LAYER_ODL_DE, f"site_status=1 AND BBOX(geom,{bbox})", False),
    ]
    now = datetime.now(timezone.utc)
    result: dict[str, list[Station] | None] = {}
    for key, layer, cql, eurdep in sources:
        try:
            async with session.get(
                WFS_URL,
                params=_params(layer, cql),
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                resp.raise_for_status()
                data = parse_body(await resp.text())
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.warning("Fetching %s failed: %s", layer, err)
            result[key] = None
            continue
        result[key] = parse_features(data.get("features") or [], eurdep, lat, lon, radius_km, max_age_h, now)
    return result
