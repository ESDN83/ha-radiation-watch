"""Constants for Radiation Watch."""

from __future__ import annotations

DOMAIN = "radiation_watch"
VERSION = "0.2.3"

# Config entry keys
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_NEAR = "radius_near"
CONF_RADIUS_FAR = "radius_far"
CONF_WIND_ENTITY = "wind_entity"
CONF_WIND_FALLBACK = "wind_fallback"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ABS_THRESHOLD = "abs_threshold"
CONF_MEDIAN_FACTOR = "median_factor"
CONF_MEDIAN_OFFSET = "median_offset"
CONF_SECTOR = "sector"
CONF_MIN_WIND = "min_wind"
CONF_MAX_AGE = "max_age"
CONF_NOTIFY_SERVICES = "notify_services"
CONF_NOTIFY_NOTABLE = "notify_notable"
CONF_NOTIFY_ALL_CLEAR = "notify_all_clear"

DEFAULT_RADIUS_NEAR = 40
DEFAULT_RADIUS_FAR = 120
DEFAULT_SCAN_INTERVAL = 30  # minutes
DEFAULT_ABS_THRESHOLD = 0.3  # uSv/h
DEFAULT_MEDIAN_FACTOR = 1.5
DEFAULT_MEDIAN_OFFSET = 0.1  # uSv/h
DEFAULT_SECTOR = 45  # degrees either side of the wind direction
DEFAULT_MIN_WIND = 2.0  # km/h, below this there is no usable direction
DEFAULT_MAX_AGE = 6  # hours, older measurements are dropped

# Early warning states (sensor device class ENUM)
STATE_CALM = "calm"
STATE_NOTABLE = "notable"
STATE_WARNING = "warning"
WARNING_STATES = [STATE_CALM, STATE_NOTABLE, STATE_WARNING]

# Open WFS service of the German Federal Office for Radiation Protection (BfS).
# It serves the German ODL network and the European EURDEP exchange.
WFS_URL = "https://www.imis.bfs.de/ogc/opendata/ows"
LAYER_EURDEP = "opendata:eurdep_latestValue"
LAYER_ODL_DE = "opendata:odlinfo_odl_1h_latest"

# URLs served by the integration
URL_BASE = "/radiation_watch_files"
URL_FRONTEND = f"{URL_BASE}/frontend"
URL_MAPS = f"{URL_BASE}/maps"
CARD_FILE = "radiation-watch-card.js"

# Map images
MAP_SIZE = 1024  # pixels, square
MAP_DIR = "radiation_watch"  # below the HA config directory
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = f"ha-radiation-watch/{VERSION} (+https://github.com/ESDN83/ha-radiation-watch)"
ATTRIBUTION_MAP = "© OpenStreetMap contributors"
ATTRIBUTION_DATA = "BfS, EURDEP"
