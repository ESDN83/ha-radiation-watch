# Radiation Watch for Home Assistant

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ESDN83&repository=ha-radiation-watch&category=integration)

Ambient dose rate stations around your home on a map, with a wind based early warning.

- Pulls the latest values of all stations within a radius you choose (default 120 km) from the open
  WFS service of the German Federal Office for Radiation Protection (BfS). It covers the German ODL
  network and the European **EURDEP** exchange (Belgium, Netherlands, Luxembourg, France and more).
- **Early warning sensor** with three states: `calm`, `notable` (a station clearly above the others),
  `warning` (such a station lies upwind, so its air is heading your way). Details such as station,
  distance and estimated arrival time are in the attributes.
- **Map card** that comes with the integration: stations in their true direction and distance,
  coloured by dose rate, the wind sector, and **travel time arcs** that show how long air from that
  distance needs to reach you at the current wind speed. Tap to switch between near and far view.
- The map background is built **once** from OpenStreetMap tiles during setup and then served by
  Home Assistant itself. No tiles are loaded while you look at the card, it works offline.
- Multilingual: English, German, French, Spanish. Adding a language is one JSON file, see below.

> This is a hobby project, **not an official warning system**. Data can be late, incomplete or wrong.
> Follow the instructions of your civil protection authorities.

## Installation

### HACS (custom repository)

1. Click the button above, or in HACS open the menu > *Custom repositories*, add
   `https://github.com/ESDN83/ha-radiation-watch` with type *Integration*.
2. Install **Radiation Watch** and restart Home Assistant.
3. *Settings > Devices & services > Add integration > Radiation Watch*.

### Manual

Copy `custom_components/radiation_watch` into your `config/custom_components` folder and restart.

## Setup

| Option | Default | Meaning |
|---|---|---|
| Latitude / longitude | your HA location | centre of the map |
| Near radius | 40 km | radius of the near view |
| Far radius | 120 km | radius of the far view and of the station search |
| Weather entity for wind | none | any `weather.*` entity with `wind_bearing` and `wind_speed` |
| Fallback weather entity | none | used when the first one has no wind data |
| Update interval | 30 min | the sources update hourly |

Later, under *Configure*, you can also tune the warning rules:

| Rule | Default | Meaning |
|---|---|---|
| Absolute threshold | 0.3 µSv/h | a station at or above this is always notable |
| Factor above median | 1.5 | notable when above median x factor ... |
| Minimum distance above median | 0.1 µSv/h | ... and above median + this |
| Wind sector | ±45° | a notable station within this angle of the wind direction raises `warning` |
| Minimum wind speed | 2 km/h | below this the direction is not used |
| Maximum data age | 6 h | older measurements are dropped |

The median is taken over all stations within the far radius, so normal regional differences
(for example lower values in Belgium than in the Eifel) do not trigger anything.

## Entities

| Entity | State | Notes |
|---|---|---|
| `sensor.radiation_watch_early_warning` | `calm` / `notable` / `warning` | attributes: wind, median, limit, `upwind` (name, country, distance, bearing, value, `eta_min`), `notable` |
| `sensor.radiation_watch_stations` | number of stations | attribute `stations`: `[name, lat, lon, µSv/h, country]`, not stored in the recorder |
| `button.radiation_watch_regenerate_map` | | downloads the tiles again and rebuilds the map images |

Example automation trigger:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.radiation_watch_early_warning
    to: warning
```

## Card

The card is registered automatically, no Lovelace resource is needed.

```yaml
type: custom:radiation-watch-card
entity: sensor.radiation_watch_early_warning   # optional, found automatically
local_sensors:                                  # optional, your own dose rate sensors in µSv/h
  - sensor.basement_dose_rate
  - entity: sensor.garden_dose_rate
    name: Garden
start_view: near          # near | far
map_style: auto           # auto (follows the theme) | light | dark | none
warn_threshold: 0.3       # yellow from (µSv/h)
danger_threshold: 1       # red from (µSv/h)
color_ok: "var(--success-color)"
color_warn: "var(--warning-color)"
color_danger: "var(--error-color)"
color_wind: "var(--primary-color)"
show_status: true         # early warning banner on top
show_legend: true
show_names: true
show_values: true
```

All options can also be set in the visual editor. Your own sensors colour the square in the middle
(highest value) and are listed below the map.

How to read it: the shaded sector is where the wind comes from. Whatever is measured on the arc
labelled "2 h" is expected here in about two hours if the wind holds. Values are 1 to 2 hours old
when they arrive, so subtract that.

## Adding a language

- Integration texts: `custom_components/radiation_watch/translations/<lang>.json`
  (generated from `tools/build_translations.py`, copy a block there or edit the JSON directly).
- Card texts: `custom_components/radiation_watch/frontend/locales/<lang>.json`, copy `en.json` and translate.

The card uses the language of your Home Assistant user and falls back to English.
Pull requests with new languages are welcome.

## Data sources and licences

- Dose rates: [BfS ODL-Info / open data](https://odlinfo.bfs.de), licence
  [Datenlizenz Deutschland Namensnennung 2.0](https://www.govdata.de/dl-de/by-2-0).
  European values come from [EURDEP](https://remap.jrc.ec.europa.eu) via the same BfS service.
- Map: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL.
  Tiles are fetched once per setup (about 50 to 100 tiles) with an identifying user agent,
  as the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) asks.
- Code: MIT, see [LICENSE](LICENSE).

## Development

```bash
python -m pytest tests
```

The calculation code in `geo.py` has no Home Assistant imports and is fully unit tested.
