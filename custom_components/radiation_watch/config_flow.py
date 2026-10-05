"""Config and options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ABS_THRESHOLD,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAX_AGE,
    CONF_MEDIAN_FACTOR,
    CONF_MEDIAN_OFFSET,
    CONF_MIN_WIND,
    CONF_NOTIFY_ALL_CLEAR,
    CONF_NOTIFY_NOTABLE,
    CONF_NOTIFY_SERVICES,
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
)


def _num(min_: float, max_: float, step: float | str, unit: str | None = None) -> selector.NumberSelector:
    cfg = selector.NumberSelectorConfig(min=min_, max=max_, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:  # the selector rejects an empty unit
        cfg["unit_of_measurement"] = unit
    return selector.NumberSelector(cfg)


WEATHER = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))


def _base_schema(d: dict) -> dict:
    """Location, radii, wind and polling. Shared by setup and options."""
    schema: dict = {
        vol.Required(CONF_LATITUDE, default=d[CONF_LATITUDE]): _num(-90, 90, "any"),
        vol.Required(CONF_LONGITUDE, default=d[CONF_LONGITUDE]): _num(-180, 180, "any"),
        vol.Required(CONF_RADIUS_NEAR, default=d.get(CONF_RADIUS_NEAR, DEFAULT_RADIUS_NEAR)): _num(10, 100, 5, "km"),
        vol.Required(CONF_RADIUS_FAR, default=d.get(CONF_RADIUS_FAR, DEFAULT_RADIUS_FAR)): _num(40, 300, 10, "km"),
    }
    # Optional entities: vol.Optional with a suggested value keeps the field clearable.
    for key in (CONF_WIND_ENTITY, CONF_WIND_FALLBACK):
        if d.get(key):
            schema[vol.Optional(key, description={"suggested_value": d[key]})] = WEATHER
        else:
            schema[vol.Optional(key)] = WEATHER
    schema[vol.Required(CONF_SCAN_INTERVAL, default=d.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))] = _num(10, 240, 5, "min")
    return schema


def _rules_schema(d: dict) -> dict:
    return {
        vol.Required(CONF_ABS_THRESHOLD, default=d.get(CONF_ABS_THRESHOLD, DEFAULT_ABS_THRESHOLD)): _num(0.05, 100, 0.01, "µSv/h"),
        vol.Required(CONF_MEDIAN_FACTOR, default=d.get(CONF_MEDIAN_FACTOR, DEFAULT_MEDIAN_FACTOR)): _num(1.1, 10, 0.1),
        vol.Required(CONF_MEDIAN_OFFSET, default=d.get(CONF_MEDIAN_OFFSET, DEFAULT_MEDIAN_OFFSET)): _num(0.01, 10, 0.01, "µSv/h"),
        vol.Required(CONF_SECTOR, default=d.get(CONF_SECTOR, DEFAULT_SECTOR)): _num(10, 90, 5, "°"),
        vol.Required(CONF_MIN_WIND, default=d.get(CONF_MIN_WIND, DEFAULT_MIN_WIND)): _num(0, 30, 0.5, "km/h"),
        vol.Required(CONF_MAX_AGE, default=d.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)): _num(1, 48, 1, "h"),
    }


def _notify_schema(hass, d: dict) -> dict:
    """Notification targets: any notify service, e.g. notify.mobile_app_phone. Empty = no notifications."""
    services = sorted(f"notify.{name}" for name in hass.services.async_services_for_domain("notify"))
    targets = selector.SelectSelector(
        selector.SelectSelectorConfig(options=services, multiple=True, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
    )
    return {
        vol.Optional(CONF_NOTIFY_SERVICES, default=list(d.get(CONF_NOTIFY_SERVICES) or [])): targets,
        vol.Required(CONF_NOTIFY_NOTABLE, default=bool(d.get(CONF_NOTIFY_NOTABLE, False))): selector.BooleanSelector(),
        vol.Required(CONF_NOTIFY_ALL_CLEAR, default=bool(d.get(CONF_NOTIFY_ALL_CLEAR, True))): selector.BooleanSelector(),
    }


def _check(user_input: dict) -> dict[str, str]:
    if user_input[CONF_RADIUS_FAR] <= user_input[CONF_RADIUS_NEAR]:
        return {CONF_RADIUS_FAR: "far_not_larger"}
    return {}


class RadiationWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # One instance only: handled by "single_config_entry" in manifest.json. A unique_id here
        # would block a second attempt with "already_in_progress" after an aborted first one.
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check(user_input)
            if not errors:
                return self.async_create_entry(title="Radiation Watch", data=user_input)
        defaults = user_input or {CONF_LATITUDE: self.hass.config.latitude, CONF_LONGITUDE: self.hass.config.longitude}
        return self.async_show_form(step_id="user", data_schema=vol.Schema(_base_schema(defaults)), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RadiationWatchOptionsFlow()


class RadiationWatchOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check(user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        d = user_input or current
        schema = {**_base_schema(d), **_rules_schema(d), **_notify_schema(self.hass, d)}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
