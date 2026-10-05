"""Radiation Watch: dose rate stations around home, wind based early warning and a map card."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FILE,
    CONF_ABS_THRESHOLD,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_AGE,
    CONF_MEDIAN_FACTOR,
    CONF_MEDIAN_OFFSET,
    CONF_MIN_WIND,
    CONF_RADIUS_FAR,
    CONF_RADIUS_NEAR,
    CONF_SCAN_INTERVAL,
    CONF_SECTOR,
    CONF_WIND_ENTITY,
    CONF_WIND_FALLBACK,
    DEFAULT_ABS_THRESHOLD,
    DEFAULT_MAX_AGE,
    DEFAULT_MEDIAN_FACTOR,
    DEFAULT_MEDIAN_OFFSET,
    DEFAULT_MIN_WIND,
    DEFAULT_RADIUS_FAR,
    DEFAULT_RADIUS_NEAR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SECTOR,
    DOMAIN,
    MAP_DIR,
    URL_FRONTEND,
    URL_MAPS,
    VERSION,
)
from .coordinator import StationCoordinator
from .mapgen import async_build_maps, maps_current, read_meta

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SIGNAL_MAPS_UPDATED = f"{DOMAIN}_maps_updated"


@dataclass
class RuntimeData:
    coordinator: StationCoordinator
    settings: dict
    map_version: int | None = None
    map_status: str = "missing"  # missing, building, ready, failed
    tasks: list = field(default_factory=list)


type RadiationWatchConfigEntry = ConfigEntry[RuntimeData]


def merged_settings(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """entry.data holds the setup values, entry.options the later changes."""
    c = {**entry.data, **entry.options}
    return {
        "latitude": float(c.get(CONF_LATITUDE, hass.config.latitude)),
        "longitude": float(c.get(CONF_LONGITUDE, hass.config.longitude)),
        "radius_near": float(c.get(CONF_RADIUS_NEAR, DEFAULT_RADIUS_NEAR)),
        "radius_far": float(c.get(CONF_RADIUS_FAR, DEFAULT_RADIUS_FAR)),
        "wind_entity": c.get(CONF_WIND_ENTITY),
        "wind_fallback": c.get(CONF_WIND_FALLBACK),
        "scan_interval": int(c.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        "abs_threshold": float(c.get(CONF_ABS_THRESHOLD, DEFAULT_ABS_THRESHOLD)),
        "median_factor": float(c.get(CONF_MEDIAN_FACTOR, DEFAULT_MEDIAN_FACTOR)),
        "median_offset": float(c.get(CONF_MEDIAN_OFFSET, DEFAULT_MEDIAN_OFFSET)),
        "sector": float(c.get(CONF_SECTOR, DEFAULT_SECTOR)),
        "min_wind": float(c.get(CONF_MIN_WIND, DEFAULT_MIN_WIND)),
        "max_age": float(c.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)),
    }


def maps_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(MAP_DIR))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card and the map images, and load the card on every dashboard."""
    folder = maps_dir(hass)
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(URL_FRONTEND, str(Path(__file__).parent / "frontend"), False),
            StaticPathConfig(URL_MAPS, str(folder), False),
        ]
    )
    # Version in the URL so browsers and the companion app fetch the new card after an update.
    card_url = f"{URL_FRONTEND}/{CARD_FILE}?v={VERSION}"
    if not await _async_register_card_resource(hass, card_url):
        add_extra_js_url(hass, card_url)
    return True


async def _async_register_card_resource(hass: HomeAssistant, card_url: str) -> bool:
    """Register the card as a dashboard resource, the way HACS does it.

    add_extra_js_url alone is not enough: the Android companion app never loaded the
    card that way (it was not even requested), while dashboard resources load everywhere.
    Only possible with resources in storage mode; YAML mode falls back to add_extra_js_url.
    """
    ll = hass.data.get(LOVELACE_DATA)
    if ll is None or ll.resource_mode != "storage":
        return False
    resources = ll.resources
    await resources.async_get_info()  # makes sure the collection is loaded
    base = card_url.split("?")[0]
    ours = [r for r in resources.async_items() if str(r.get("url", "")).split("?")[0] == base]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": card_url})
        return True
    if ours[0].get("url") != card_url:
        await resources.async_update_item(ours[0]["id"], {"res_type": "module", "url": card_url})
    for extra in ours[1:]:
        await resources.async_delete_item(extra["id"])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RadiationWatchConfigEntry) -> bool:
    settings = merged_settings(hass, entry)
    coordinator = StationCoordinator(hass, entry, settings)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = RuntimeData(coordinator=coordinator, settings=settings)

    folder = maps_dir(hass)
    current = await hass.async_add_executor_job(
        maps_current, folder, settings["latitude"], settings["longitude"], settings["radius_near"], settings["radius_far"]
    )
    if current:
        meta = await hass.async_add_executor_job(read_meta, folder)
        entry.runtime_data.map_version = meta.get("version")
        entry.runtime_data.map_status = "ready"
    else:
        async_start_map_build(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


def async_start_map_build(hass: HomeAssistant, entry: RadiationWatchConfigEntry) -> None:
    """Build the map images in the background, setup does not wait for the download."""
    rd = entry.runtime_data
    if rd.map_status == "building":
        return
    rd.map_status = "building"

    async def _build() -> None:
        s = rd.settings
        try:
            rd.map_version = await async_build_maps(
                hass, async_get_clientsession(hass), maps_dir(hass),
                s["latitude"], s["longitude"], s["radius_near"], s["radius_far"],
            )
            rd.map_status = "ready"
        except Exception as err:  # noqa: BLE001 - any failure only means: no background map
            rd.map_status = "failed"
            _LOGGER.warning("Building the map images failed, the card works without them: %s", err)
        async_dispatcher_send(hass, SIGNAL_MAPS_UPDATED)

    entry.async_create_background_task(hass, _build(), f"{DOMAIN}_build_maps")


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RadiationWatchConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Integration removed: take the card resource out of the dashboards again."""
    ll = hass.data.get(LOVELACE_DATA)
    if ll is None or ll.resource_mode != "storage":
        return
    base = f"{URL_FRONTEND}/{CARD_FILE}"
    for r in list(ll.resources.async_items()):
        if str(r.get("url", "")).split("?")[0] == base:
            await ll.resources.async_delete_item(r["id"])
