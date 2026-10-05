"""Event entity: fires when the early warning level changes (warning, notable, all_clear)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RadiationWatchConfigEntry
from .sensor import device_info

EVENT_TYPES = ["warning", "notable", "all_clear"]


async def async_setup_entry(
    hass: HomeAssistant, entry: RadiationWatchConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([AlertEvent(entry)])


class AlertEvent(EventEntity):
    """Use it in automations with the event trigger, event data carries title, message and stations."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "alert"
    _attr_event_types = EVENT_TYPES

    def __init__(self, entry: RadiationWatchConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_alert"
        self.entity_id = "event.radiation_watch_alert"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        engine = self._entry.runtime_data.engine
        engine.alert_listeners.append(self._on_alert)
        self.async_on_remove(lambda: engine.alert_listeners.remove(self._on_alert))

    @callback
    def _on_alert(self, event_type: str, data: dict) -> None:
        self._trigger_event(event_type, data)
        self.async_write_ha_state()
