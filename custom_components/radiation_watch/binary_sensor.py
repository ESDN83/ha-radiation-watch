"""Binary sensor: on while the early warning is at level warning."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RadiationWatchConfigEntry
from .const import STATE_WARNING
from .sensor import EngineEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RadiationWatchConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([WarningBinarySensor(entry)])


class WarningBinarySensor(EngineEntity, BinarySensorEntity):
    """Simple trigger for automations: on = elevated radiation upwind."""

    _attr_translation_key = "warning"
    _attr_device_class = BinarySensorDeviceClass.SAFETY  # on means unsafe

    def __init__(self, entry: RadiationWatchConfigEntry) -> None:
        super().__init__(entry, "warning", "binary_sensor.radiation_watch_warning")

    @property
    def is_on(self) -> bool | None:
        r = self.engine.state.result
        return None if r is None else r.state == STATE_WARNING

    @property
    def extra_state_attributes(self) -> dict:
        r = self.engine.state.result
        return {"message": self.engine.state.message, "upwind": r.upwind[:10] if r else []}
