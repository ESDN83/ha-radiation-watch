"""Background map images, built once from OpenStreetMap tiles and then served locally.

The images use the same flat projection as the card (see geo.offset_km): x = east km, y = north km,
home in the centre. Tiles are Web Mercator, so every output pixel is mapped back to its tile pixel.
Downloading happens only when the location or a radius changes, or on the "Regenerate map" button.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import time
from pathlib import Path

import aiohttp

from .const import MAP_SIZE, TILE_URL, USER_AGENT
from .geo import KM_PER_DEG_LAT, zoom_for

_LOGGER = logging.getLogger(__name__)
META_FILE = "meta.json"


def _merc(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2**z * 256
    x = (lon + 180) / 360 * n
    lr = math.radians(lat)
    y = (1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n
    return x, y


def _needed_tiles(lat: float, lon: float, radius_km: float, z: int) -> set[tuple[int, int]]:
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = radius_km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    x0, y0 = _merc(lat + dlat, lon - dlon, z)
    x1, y1 = _merc(lat - dlat, lon + dlon, z)
    return {(tx, ty) for tx in range(int(x0 // 256), int(x1 // 256) + 1) for ty in range(int(y0 // 256), int(y1 // 256) + 1)}


def _render(tiles: dict[tuple[int, int], bytes], lat: float, lon: float, radius_km: float, z: int, out_dir: Path, name: str) -> None:
    """Runs in the executor: build the light image and a dark variant for dark themes."""
    from PIL import Image, ImageOps  # Pillow ships with Home Assistant

    decoded = {k: Image.open(io.BytesIO(v)).convert("RGB") for k, v in tiles.items()}
    blank = Image.new("RGB", (256, 256), (200, 200, 200))
    out = Image.new("RGB", (MAP_SIZE, MAP_SIZE))
    px = out.load()
    kx = KM_PER_DEG_LAT * math.cos(math.radians(lat))
    for j in range(MAP_SIZE):
        dy = radius_km - (j + 0.5) / MAP_SIZE * 2 * radius_km
        for i in range(MAP_SIZE):
            dx = (i + 0.5) / MAP_SIZE * 2 * radius_km - radius_km
            x, y = _merc(lat + dy / KM_PER_DEG_LAT, lon + dx / kx, z)
            tile = decoded.get((int(x // 256), int(y // 256)), blank)
            px[i, j] = tile.getpixel((int(x % 256), int(y % 256)))
    out.save(out_dir / f"{name}_light.jpg", quality=85)

    # Dark: invert, turn the hue by 180 degrees (water stays blue, forest green), mute and dim.
    h, s, v = ImageOps.invert(out).convert("HSV").split()
    h = h.point(lambda p: (p + 128) % 256)
    s = s.point(lambda p: int(p * 0.6))
    v = v.point(lambda p: int(p * 0.85))
    Image.merge("HSV", (h, s, v)).convert("RGB").save(out_dir / f"{name}_dark.jpg", quality=85)


def read_meta(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / META_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def maps_current(out_dir: Path, lat: float, lon: float, near: float, far: float) -> bool:
    meta = read_meta(out_dir)
    files_ok = all((out_dir / f"{n}_{s}.jpg").exists() for n in ("near", "far") for s in ("light", "dark"))
    return files_ok and meta.get("params") == [round(lat, 5), round(lon, 5), near, far, MAP_SIZE]


async def async_build_maps(
    hass, session: aiohttp.ClientSession, out_dir: Path, lat: float, lon: float, near: float, far: float
) -> int:
    """Download the tiles and write near/far images in light and dark. Returns a version stamp."""
    await hass.async_add_executor_job(lambda: out_dir.mkdir(parents=True, exist_ok=True))
    total = 0
    for name, radius in (("near", near), ("far", far)):
        z = zoom_for(radius, MAP_SIZE, lat)
        tiles: dict[tuple[int, int], bytes] = {}
        for tx, ty in sorted(_needed_tiles(lat, lon, radius, z)):
            url = TILE_URL.format(z=z, x=tx, y=ty)
            async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                tiles[(tx, ty)] = await resp.read()
            await asyncio.sleep(0.2)  # be gentle with the OSM tile servers
        total += len(tiles)
        await hass.async_add_executor_job(_render, tiles, lat, lon, radius, z, out_dir, name)
    stamp = int(time.time())
    meta = {"params": [round(lat, 5), round(lon, 5), near, far, MAP_SIZE], "version": stamp, "tiles": total}
    await hass.async_add_executor_job(lambda: (out_dir / META_FILE).write_text(json.dumps(meta), encoding="utf-8"))
    _LOGGER.info("Radiation Watch maps built from %s OSM tiles", total)
    return stamp
