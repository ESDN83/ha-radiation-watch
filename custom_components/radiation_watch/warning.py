"""Central early warning evaluation, message texts and notifications.

One evaluation feeds all entities (status sensor, warning binary sensor, message sensor,
alert event). It runs when the station list is refreshed and when a wind entity changes.
On a change of level the alert event fires and, if configured, notifications go out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, STATE_CALM, STATE_NOTABLE, STATE_WARNING
from .geo import Evaluation, Rules, evaluate, to_kmh

_LOGGER = logging.getLogger(__name__)
SIGNAL_EVALUATED = f"{DOMAIN}_evaluated"
MESSAGES_DIR = Path(__file__).parent / "messages"
DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def load_messages(language: str) -> dict:
    """Message texts in the HA language, English as fallback. Runs in the executor."""
    texts = json.loads((MESSAGES_DIR / "en.json").read_text(encoding="utf-8"))
    path = MESSAGES_DIR / f"{language.split('-')[0]}.json"
    if path.is_file():
        texts.update(json.loads(path.read_text(encoding="utf-8")))
    return texts


def _fmt(value: float, decimals: int, decimal_comma: bool) -> str:
    s = f"{value:.{decimals}f}"
    return s.replace(".", ",") if decimal_comma else s


def _eta(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def _join(t: dict, items: list[str], limit: int = 255) -> str:
    """Nearest stations first, as many as fit into a sensor state; the rest as "and N more"."""
    text, used = "", 0
    for item in items:
        candidate = item if not text else f"{text}; {item}"
        rest = len(items) - used - 1
        tail = f" {t['more'].format(n=rest)}" if rest else ""
        if len(candidate + tail) > limit:
            break
        text, used = candidate, used + 1
    if not text and items:
        text, used = items[0][: limit - 1], 1
    if used < len(items):
        text += f" {t['more'].format(n=len(items) - used)}"
    return text


def build_message(t: dict, result: Evaluation, radius_far: float) -> tuple[str, str]:
    """(title, text) for the current level. Text stays under 255 characters for a sensor state."""
    comma = t.get("decimal_comma", False)
    dirs = t.get("directions", DIRECTIONS)
    if result.state == STATE_WARNING:
        items = [
            t["warning_item"].format(
                name=i["name"] + (f" ({i['country']})" if i["country"] != "DE" else ""),
                km=_fmt(i["distance_km"], 0, comma),
                value=_fmt(i["value"], 3, comma),
                eta=_eta(i["eta_min"]),
            )
            for i in result.upwind
        ]
        return t["title_warning"], _join(t, items)
    if result.state == STATE_NOTABLE:
        items = [
            t["notable_item"].format(
                name=i["name"] + (f" ({i['country']})" if i["country"] != "DE" else ""),
                km=_fmt(i["distance_km"], 0, comma),
                value=_fmt(i["value"], 3, comma),
                dir=dirs[round(i["bearing"] / 45) % 8],
            )
            for i in result.notable
        ]
        return t["title_notable"], _join(t, items)
    return t["title_calm"], t["calm"].format(km=_fmt(radius_far, 0, comma))


@dataclass
class WarningState:
    """Latest evaluation, shared by all entities of the entry."""

    result: Evaluation | None = None
    wind_bearing: float | None = None
    wind_kmh: float | None = None
    wind_source: str | None = None
    title: str = ""
    message: str = ""
    last_level: str | None = None
    no_data: bool = False  # no station younger than max_age (internet or data service down)
    fresh_count: int = 0
    stale_count: int = 0
    data_time: str | None = None  # newest measurement, ISO
    listeners: list = field(default_factory=list)


class WarningEngine:
    def __init__(self, hass: HomeAssistant, entry, settings: dict, coordinator, texts: dict) -> None:
        self.hass = hass
        self.entry = entry
        self.settings = settings
        self.coordinator = coordinator
        self.texts = texts
        self.state = WarningState()
        self.alert_listeners: list = []  # callables (event_type, data) from the event entity

    @callback
    def async_start(self) -> None:
        s = self.settings
        wind = [e for e in (s["wind_entity"], s["wind_fallback"]) if e]
        if wind:
            self.entry.async_on_unload(async_track_state_change_event(self.hass, wind, self._wind_changed))
        self.entry.async_on_unload(self.coordinator.async_add_listener(self.async_evaluate))
        self.async_evaluate()

    @callback
    def _wind_changed(self, event: Event[EventStateChangedData]) -> None:
        self.async_evaluate()

    def _wind(self) -> tuple[float | None, float | None, str | None]:
        """First source with usable wind (>= min_wind), else the first one with any wind data.

        A garden anemometer often reads 0 at night while the regional wind keeps blowing, and for a
        plume the regional wind counts. So a calm main source hands over to the fallback.
        """
        s = self.settings
        readings = []
        for entity_id in (s["wind_entity"], s["wind_fallback"]):
            if not entity_id or (st := self.hass.states.get(entity_id)) is None:
                continue
            bearing, speed = st.attributes.get("wind_bearing"), st.attributes.get("wind_speed")
            if isinstance(bearing, (int, float)) and isinstance(speed, (int, float)):
                readings.append((float(bearing), to_kmh(float(speed), st.attributes.get("wind_speed_unit")), entity_id))
        for reading in readings:
            if reading[1] >= s["min_wind"]:
                return reading
        return readings[0] if readings else (None, None, None)

    @callback
    def async_evaluate(self) -> None:
        s = self.settings
        rules = Rules(s["abs_threshold"], s["median_factor"], s["median_offset"], s["sector"], s["min_wind"])
        bearing, kmh, source = self._wind()
        st = self.state
        st.wind_bearing, st.wind_kmh, st.wind_source = bearing, kmh, source

        # Without internet the last list stays, but its values get old. Outdated stations must not
        # count, otherwise a stale list would keep reporting "calm".
        stations = self.coordinator.data.stations
        oldest = time.time() - s["max_age"] * 3600
        fresh = [x for x in stations if x.measured is None or x.measured >= oldest]
        times = [x.measured for x in stations if x.measured]
        st.fresh_count, st.stale_count = len(fresh), len(stations) - len(fresh)
        st.data_time = datetime.fromtimestamp(max(times), timezone.utc).isoformat() if times else None
        if not fresh:
            # Level stays as it was for the change detection, so no event fires when data come back.
            st.result, st.no_data = None, True
            st.title, st.message = self.texts["title_no_data"], self.texts["no_data"]
            async_dispatcher_send(self.hass, f"{SIGNAL_EVALUATED}_{self.entry.entry_id}")
            return
        st.no_data = False

        result = evaluate(fresh, s["latitude"], s["longitude"], bearing, kmh, rules)
        st.result = result
        st.title, st.message = build_message(self.texts, result, s["radius_far"])

        previous, st.last_level = st.last_level, result.state
        if previous != result.state:
            self._level_changed(previous, result.state)
        async_dispatcher_send(self.hass, f"{SIGNAL_EVALUATED}_{self.entry.entry_id}")

    @callback
    def _level_changed(self, previous: str | None, level: str) -> None:
        """Fire the alert event and send notifications on a change of level.

        Right after startup (previous None) only a warning counts, so a restart does not
        report "all clear" or repeat a notable station.
        """
        if previous is None and level != STATE_WARNING:
            return
        event_type = "all_clear" if level == STATE_CALM else level
        data = {
            "level": level,
            "previous": previous,
            "title": self.state.title,
            "message": self.state.message,
            "upwind": self.state.result.upwind[:10],
            "notable": self.state.result.notable[:10],
        }
        for listener in list(self.alert_listeners):
            listener(event_type, data)

        s = self.settings
        wanted = {STATE_WARNING} | ({STATE_NOTABLE} if s["notify_notable"] else set())
        if s["notify_all_clear"] and previous in (STATE_WARNING, STATE_NOTABLE):
            wanted.add(STATE_CALM)
        if level in wanted and s["notify_services"]:
            self.hass.async_create_task(self._notify(level))

    async def _notify(self, level: str) -> None:
        for service in self.settings["notify_services"]:
            domain, _, name = service.partition(".")
            if not name:
                domain, name = "notify", service
            title = self.texts["title_all_clear"] if level == STATE_CALM else self.state.title
            payload = {"title": title, "message": self.state.message}
            if level == STATE_WARNING and service.startswith("notify.mobile_app_"):
                # Android: high priority so it arrives while the phone sleeps; iOS: time sensitive.
                payload["data"] = {"priority": "high", "ttl": 0, "push": {"interruption-level": "time-sensitive"}}
            try:
                await self.hass.services.async_call(domain, name, payload, blocking=False)
            except Exception as err:  # noqa: BLE001 - one broken target must not stop the others
                _LOGGER.warning("Radiation Watch could not notify %s: %s", service, err)
