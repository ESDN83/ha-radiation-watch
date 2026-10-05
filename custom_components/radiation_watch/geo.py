"""Pure calculation helpers. No Home Assistant imports, so they can be unit tested directly."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

KM_PER_DEG_LAT = 111.2


@dataclass(frozen=True)
class Station:
    """One measuring station with its latest dose rate."""

    name: str
    latitude: float
    longitude: float
    value: float  # uSv/h
    country: str  # ISO code, "DE" for the German ODL network


@dataclass(frozen=True)
class Rules:
    """When a station counts as notable and when that becomes a warning."""

    abs_threshold: float = 0.3
    median_factor: float = 1.5
    median_offset: float = 0.1
    sector: float = 45.0
    min_wind: float = 2.0


@dataclass
class Evaluation:
    """Result of one early warning evaluation."""

    state: str
    median: float | None
    limit: float | None
    notable: list[dict] = field(default_factory=list)
    upwind: list[dict] = field(default_factory=list)


def offset_km(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """East and north offset in km. Flat approximation, good to well under 1 % within 150 km.

    The card and the map images use exactly the same projection, so dots and map stay aligned.
    """
    dy = (lat - lat0) * KM_PER_DEG_LAT
    dx = (lon - lon0) * KM_PER_DEG_LAT * math.cos(math.radians(lat0))
    return dx, dy


def distance_bearing(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """Distance in km and compass bearing (0 = north, clockwise) from the home point."""
    dx, dy = offset_km(lat0, lon0, lat, lon)
    return math.hypot(dx, dy), (math.degrees(math.atan2(dx, dy)) + 360) % 360


def angle_diff(a: float, b: float) -> float:
    """Smallest difference between two compass angles, 0 to 180."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def median(values: list[float]) -> float | None:
    """Upper median, the same definition the card uses."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def notable_limit(med: float, rules: Rules) -> float:
    """A station above this (or above abs_threshold) is notable."""
    return max(med * rules.median_factor, med + rules.median_offset)


def evaluate(
    stations: list[Station],
    lat0: float,
    lon0: float,
    wind_bearing: float | None,
    wind_kmh: float | None,
    rules: Rules,
) -> Evaluation:
    """Classify the situation.

    calm:    no station stands out.
    notable: at least one station is above the limit, but not upwind.
    warning: a notable station lies in the direction the wind comes from
             (wind_bearing +- sector), so its air is heading towards home.
    """
    med = median([s.value for s in stations])
    if med is None:
        return Evaluation(state="calm", median=None, limit=None)
    limit = notable_limit(med, rules)
    has_wind = wind_bearing is not None and wind_kmh is not None and wind_kmh >= rules.min_wind

    notable: list[dict] = []
    upwind: list[dict] = []
    for s in stations:
        if s.value < rules.abs_threshold and s.value < limit:
            continue
        dist, bearing = distance_bearing(lat0, lon0, s.latitude, s.longitude)
        item = {
            "name": s.name,
            "country": s.country,
            "value": s.value,
            "distance_km": round(dist, 1),
            "bearing": round(bearing),
        }
        notable.append(item)
        if has_wind and angle_diff(bearing, wind_bearing) <= rules.sector:
            item = {**item, "eta_min": round(dist / wind_kmh * 60)}
            upwind.append(item)

    notable.sort(key=lambda i: i["distance_km"])
    upwind.sort(key=lambda i: i["distance_km"])
    state = "warning" if upwind else ("notable" if notable else "calm")
    return Evaluation(state=state, median=med, limit=round(limit, 4), notable=notable, upwind=upwind)


def to_kmh(speed: float | None, unit: str | None) -> float | None:
    """Convert a weather entity wind speed to km/h."""
    if speed is None:
        return None
    factors = {"km/h": 1.0, "m/s": 3.6, "mph": 1.609344, "kn": 1.852, "ft/s": 1.09728}
    return speed * factors.get(unit or "km/h", 1.0)


def zoom_for(radius_km: float, size_px: int, lat: float) -> int:
    """OSM zoom level whose resolution best matches the map image, labels then stay readable."""
    km_per_px = 2 * radius_km / size_px
    equator_km_per_px_z0 = 40075.016686 * math.cos(math.radians(lat)) / 256
    z = round(math.log2(equator_km_per_px_z0 / km_per_px))
    return max(5, min(14, z))
