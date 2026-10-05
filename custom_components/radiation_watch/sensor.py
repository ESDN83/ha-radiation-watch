"""Sensors: station list and early warning."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SIGNAL_MAPS_UPDATED, RadiationWatchConfigEntry
from .const import ATTRIBUTION_DATA, ATTRIBUTION_MAP, DOMAIN, URL_MAPS, VERSION, WARNING_STATES
from .coordinator import StationCoordinator
from .geo import Rules, evaluate, to_kmh


def device_info(entry: RadiationWatchConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Radiation Watch",
        manufacturer="ESDN83",
        model="BfS / EURDEP",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: RadiationWatchConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    stations = StationsSensor(entry)
    async_add_entities([stations, EarlyWarningSensor(entry, stations)])


class StationsSensor(CoordinatorEntity[StationCoordinator], SensorEntity):
    """Number of stations, the full list as attribute (kept out of the recorder)."""

    _attr_has_entity_name = True
    _attr_translation_key = "stations"
    _attr_icon = "mdi:map-marker-radius"
    _attr_native_unit_of_measurement = "stations"
    _attr_attribution = ATTRIBUTION_DATA
    # About 10 KB every poll, history of it is worthless and would bloat the database.
    _unrecorded_attributes = frozenset({"stations"})

    def __init__(self, entry: RadiationWatchConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_stations"
        # Fixed English entity_id, otherwise it follows the UI language (sensor.radiation_watch_stationen ...).
        self.entity_id = "sensor.radiation_watch_stations"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.stations)

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {
            # Compact: [name, latitude, longitude, uSv/h, country]
            "stations": [[s.name, s.latitude, s.longitude, s.value, s.country] for s in d.stations],
            "fetched_at": d.fetched_at.isoformat(),
        }


class EarlyWarningSensor(CoordinatorEntity[StationCoordinator], SensorEntity):
    """calm / notable / warning. Everything the card needs is in the attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "early_warning"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = WARNING_STATES
    _attr_attribution = f"{ATTRIBUTION_DATA}, {ATTRIBUTION_MAP}"
    _unrecorded_attributes = frozenset({"notable", "maps", "rules", "radius_near", "radius_far", "home"})

    def __init__(self, entry: RadiationWatchConfigEntry, stations: StationsSensor) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._stations_sensor = stations
        self._attr_unique_id = f"{entry.entry_id}_early_warning"
        self.entity_id = "sensor.radiation_watch_early_warning"
        self._attr_device_info = device_info(entry)
        self._attrs: dict = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        s = self._entry.runtime_data.settings
        wind = [e for e in (s["wind_entity"], s["wind_fallback"]) if e]
        if wind:
            self.async_on_remove(async_track_state_change_event(self.hass, wind, self._wind_changed))
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_MAPS_UPDATED, self._maps_changed))
        self._recalc()

    @callback
    def _wind_changed(self, event: Event[EventStateChangedData]) -> None:
        self._recalc()
        self.async_write_ha_state()

    @callback
    def _maps_changed(self) -> None:
        self._recalc()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._recalc()
        super()._handle_coordinator_update()

    def _wind(self) -> tuple[float | None, float | None, str | None]:
        """Bearing (where the wind comes from) and speed in km/h from the first usable weather entity."""
        s = self._entry.runtime_data.settings
        for entity_id in (s["wind_entity"], s["wind_fallback"]):
            if not entity_id:
                continue
            st: State | None = self.hass.states.get(entity_id)
            if st is None:
                continue
            bearing = st.attributes.get("wind_bearing")
            speed = st.attributes.get("wind_speed")
            if isinstance(bearing, (int, float)) and isinstance(speed, (int, float)):
                return float(bearing), to_kmh(float(speed), st.attributes.get("wind_speed_unit")), entity_id
        return None, None, None

    def _recalc(self) -> None:
        rd = self._entry.runtime_data
        s = rd.settings
        rules = Rules(s["abs_threshold"], s["median_factor"], s["median_offset"], s["sector"], s["min_wind"])
        bearing, kmh, source = self._wind()
        result = evaluate(self.coordinator.data.stations, s["latitude"], s["longitude"], bearing, kmh, rules)
        self._attr_native_value = result.state
        maps = None
        if rd.map_status == "ready" and rd.map_version:
            maps = {
                f"{n}_{st}": f"{URL_MAPS}/{n}_{st}.jpg?v={rd.map_version}"
                for n in ("near", "far")
                for st in ("light", "dark")
            }
        self._attrs = {
            "wind_bearing": bearing,
            "wind_speed_kmh": round(kmh, 1) if kmh is not None else None,
            "wind_source": source,
            "median": result.median,
            "limit": result.limit,
            "notable_count": len(result.notable),
            "upwind": result.upwind[:10],
            "notable": result.notable[:30],
            "stations_entity": self._stations_sensor.entity_id,
            "home": [s["latitude"], s["longitude"]],
            "radius_near": s["radius_near"],
            "radius_far": s["radius_far"],
            "rules": {
                "abs_threshold": s["abs_threshold"],
                "median_factor": s["median_factor"],
                "median_offset": s["median_offset"],
                "sector": s["sector"],
                "min_wind": s["min_wind"],
            },
            "maps": maps,
            "map_status": rd.map_status,
            "fetched_at": self.coordinator.data.fetched_at.isoformat(),
        }

    @property
    def extra_state_attributes(self) -> dict:
        return self._attrs
