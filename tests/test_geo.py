"""Unit tests for the pure calculation module (no Home Assistant needed).

Run: python -m pytest tests
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "geo", Path(__file__).resolve().parent.parent / "custom_components" / "radiation_watch" / "geo.py"
)
geo = importlib.util.module_from_spec(_spec)
sys.modules["geo"] = geo  # dataclasses look the module up by name
_spec.loader.exec_module(geo)

HOME = (50.7327636, 6.5145581)


def st(name, lat, lon, value, country="DE"):
    return geo.Station(name, lat, lon, value, country)


def test_distance_bearing_known_stations():
    # Reference values checked against the BfS integration (distance_km attribute).
    d, b = geo.distance_bearing(*HOME, 50.73, 6.59)  # Vettweiss
    assert d == pytest.approx(5.32, abs=0.05)
    assert b == pytest.approx(93, abs=1)
    d, b = geo.distance_bearing(*HOME, 50.72, 6.40)  # Huertgenwald-Kleinhau
    assert d == pytest.approx(8.19, abs=0.1)
    assert b == pytest.approx(260, abs=1)


def test_angle_diff_wraps():
    assert geo.angle_diff(350, 10) == 20
    assert geo.angle_diff(10, 350) == 20
    assert geo.angle_diff(0, 180) == 180


def test_median_upper():
    assert geo.median([]) is None
    assert geo.median([3, 1, 2]) == 2
    assert geo.median([1, 2, 3, 4]) == 3


def test_limit():
    rules = geo.Rules()
    assert geo.notable_limit(0.1, rules) == pytest.approx(0.2)  # offset wins at low median
    assert geo.notable_limit(0.4, rules) == pytest.approx(0.6)  # factor wins at high median


def _background():
    return [st(f"S{i}", HOME[0] + 0.2 * (i % 3 - 1), HOME[1] + 0.2 * (i % 5 - 2), 0.11) for i in range(15)]


def test_calm():
    r = geo.evaluate(_background(), *HOME, 270, 20, geo.Rules())
    assert r.state == "calm"
    assert r.median == pytest.approx(0.11)


def test_notable_but_not_upwind():
    # Euskirchen lies east-south-east, wind from west: notable only.
    stations = _background() + [st("Euskirchen", 50.66, 6.79, 0.5)]
    r = geo.evaluate(stations, *HOME, 270, 20, geo.Rules())
    assert r.state == "notable"
    assert r.upwind == []
    assert r.notable[0]["name"] == "Euskirchen"


def test_warning_upwind_with_eta():
    # Tihange lies about 90 km west-south-west, wind from 255 degrees at 15 km/h.
    stations = _background() + [st("Tihange", 50.53, 5.27, 0.9, "BE")]
    r = geo.evaluate(stations, *HOME, 255, 15, geo.Rules())
    assert r.state == "warning"
    hit = r.upwind[0]
    assert hit["country"] == "BE"
    assert hit["distance_km"] == pytest.approx(90.6, abs=1.5)
    assert hit["eta_min"] == pytest.approx(hit["distance_km"] / 15 * 60, abs=1)


def test_no_warning_in_calm_air():
    stations = _background() + [st("Tihange", 50.53, 5.27, 0.9, "BE")]
    r = geo.evaluate(stations, *HOME, 255, 1.0, geo.Rules())  # below min_wind
    assert r.state == "notable"


def test_relative_rise_counts_below_absolute_threshold():
    # 0.25 is below 0.3 but above median 0.11 + 0.1.
    stations = _background() + [st("Simmerath", 50.6, 6.3, 0.25)]
    r = geo.evaluate(stations, *HOME, 225, 10, geo.Rules())
    assert r.state == "warning"


def test_wind_units():
    assert geo.to_kmh(10, "m/s") == pytest.approx(36)
    assert geo.to_kmh(10, "km/h") == 10
    assert geo.to_kmh(None, "m/s") is None


def test_zoom_levels():
    assert geo.zoom_for(40, 1024, 50.7) == 10
    assert geo.zoom_for(120, 1024, 50.7) == 9
