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


def _num(min_: float, max_: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=min_, max=max_, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX)
    )


WEATHER = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))


def _base_schema(d: dict) -> dict:
    """Location, radii, wind and polling. Shared by setup and options."""
    schema: dict = {
        vol.Required(CONF_LATITUDE, default=d[CONF_LATITUDE]): _num(-90, 90, 0.00001),
        vol.Required(CONF_LONGITUDE, default=d[CONF_LONGITUDE]): _num(-180, 180, 0.00001),
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


def _check(user_input: dict) -> dict[str, str]:
    if user_input[CONF_RADIUS_FAR] <= user_input[CONF_RADIUS_NEAR]:
        return {CONF_RADIUS_FAR: "far_not_larger"}
    return {}


class RadiationWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
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
        schema = {**_base_schema(user_input or current), **_rules_schema(user_input or current)}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
