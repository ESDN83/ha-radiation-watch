"""Button: download the map tiles again and rebuild the images."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RadiationWatchConfigEntry, async_start_map_build
from .sensor import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: RadiationWatchConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([RegenerateMapButton(entry)])


class RegenerateMapButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "regenerate_map"
    _attr_icon = "mdi:map-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: RadiationWatchConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_regenerate_map"
        self._attr_device_info = device_info(entry)

    async def async_press(self) -> None:
        async_start_map_build(self.hass, self._entry)
