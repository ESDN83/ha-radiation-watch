"""Sensors: station list, early warning level and ready-made message text."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SIGNAL_MAPS_UPDATED, RadiationWatchConfigEntry
from .const import ATTRIBUTION_DATA, ATTRIBUTION_MAP, DOMAIN, URL_MAPS, VERSION, WARNING_STATES
from .coordinator import StationCoordinator
from .warning import SIGNAL_EVALUATED


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
    async_add_entities([stations, EarlyWarningSensor(entry, stations), MessageSensor(entry)])


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


class EngineEntity(Entity):
    """Base for entities that show the shared early warning evaluation."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: RadiationWatchConfigEntry, key: str, entity_id: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self.entity_id = entity_id
        self._attr_device_info = device_info(entry)

    @property
    def engine(self):
        return self._entry.runtime_data.engine

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{SIGNAL_EVALUATED}_{self._entry.entry_id}", self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        return self.engine.state.result is not None


class EarlyWarningSensor(EngineEntity, SensorEntity):
    """calm / notable / warning. Everything the card needs is in the attributes."""

    _attr_translation_key = "early_warning"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = WARNING_STATES
    _attr_attribution = f"{ATTRIBUTION_DATA}, {ATTRIBUTION_MAP}"
    _unrecorded_attributes = frozenset({"notable", "maps", "rules", "radius_near", "radius_far", "home"})

    def __init__(self, entry: RadiationWatchConfigEntry, stations: StationsSensor) -> None:
        super().__init__(entry, "early_warning", "sensor.radiation_watch_early_warning")
        self._stations_sensor = stations

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_MAPS_UPDATED, self._maps_changed))

    @callback
    def _maps_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        r = self.engine.state.result
        return r.state if r else None

    @property
    def extra_state_attributes(self) -> dict:
        rd = self._entry.runtime_data
        s = rd.settings
        st = rd.engine.state
        r = st.result
        maps = None
        if rd.map_status == "ready" and rd.map_version:
            maps = {
                f"{n}_{v}": f"{URL_MAPS}/{n}_{v}.jpg?v={rd.map_version}" for n in ("near", "far") for v in ("light", "dark")
            }
        return {
            "wind_bearing": st.wind_bearing,
            "wind_speed_kmh": round(st.wind_kmh, 1) if st.wind_kmh is not None else None,
            "wind_source": st.wind_source,
            "median": r.median if r else None,
            "limit": r.limit if r else None,
            "notable_count": len(r.notable) if r else 0,
            "upwind": r.upwind[:10] if r else [],
            "notable": r.notable[:30] if r else [],
            "message": st.message,
            "stations_entity": self._stations_sensor.entity_id,
            "home": [s["latitude"], s["longitude"]],
            "radius_near": s["radius_near"],
            "radius_far": s["radius_far"],
            "rules": {k: s[k] for k in ("abs_threshold", "median_factor", "median_offset", "sector", "min_wind")},
            "maps": maps,
            "map_status": rd.map_status,
            "fetched_at": self._entry.runtime_data.coordinator.data.fetched_at.isoformat(),
        }


class MessageSensor(EngineEntity, SensorEntity):
    """Ready-made text in the HA language, for notifications, TTS or a dashboard line."""

    _attr_translation_key = "message"
    _attr_icon = "mdi:message-alert-outline"

    def __init__(self, entry: RadiationWatchConfigEntry) -> None:
        super().__init__(entry, "message", "sensor.radiation_watch_message")

    @property
    def native_value(self) -> str:
        return self.engine.state.message[:255]

    @property
    def extra_state_attributes(self) -> dict:
        r = self.engine.state.result
        return {"title": self.engine.state.title, "level": r.state if r else None}
