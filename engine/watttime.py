from __future__ import annotations

import base64
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

_USERNAME = os.getenv("WATTTIME_USERNAME")
_PASSWORD = os.getenv("WATTTIME_PASSWORD")
_BASE_URL = "https://api.watttime.org"

# Simple in-process token cache; re-auth after 29 min (tokens last 30 min)
_token: str | None = None
_token_expiry: float = 0.0


def _get_token() -> str:
    global _token, _token_expiry
    if _token and time.time() < _token_expiry:
        return _token
    if not _USERNAME or not _PASSWORD:
        raise RuntimeError("WATTTIME_USERNAME / WATTTIME_PASSWORD not set in environment")
    credentials = base64.b64encode(f"{_USERNAME}:{_PASSWORD}".encode()).decode()
    resp = requests.post(
        f"{_BASE_URL}/login",
        headers={"Authorization": f"Basic {credentials}"},
        timeout=10,
    )
    resp.raise_for_status()
    _token = resp.json()["token"]
    _token_expiry = time.time() + 60 * 29
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


def geocode(location_str: str) -> tuple[float, float] | None:
    """Convert a location string to (lat, lon) via OpenStreetMap Nominatim."""
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location_str, "format": "json", "limit": 1},
        headers={"User-Agent": "ResourXe/1.0 (compute-routing-engine)"},
        timeout=10,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def get_region(lat: float, lon: float) -> str | None:
    """Return the WattTime balancing-authority region abbreviation for a coordinate."""
    resp = requests.get(
        f"{_BASE_URL}/v3/region-from-loc",
        params={"latitude": lat, "longitude": lon, "signal_type": "co2_moer"},
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("region")


def get_signal_index(region: str) -> dict | None:
    """
    Return the current carbon signal index for a region.
    'percent' is 0–100 where lower = cleaner (free-tier metric).
    Returns None when the region has no WattTime coverage.
    """
    resp = requests.get(
        f"{_BASE_URL}/v3/signal-index",
        params={"region": region, "signal_type": "co2_moer"},
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return None
    latest = data[0]
    return {
        "region": region,
        "percent": latest.get("value"),   # 0 = cleanest, 100 = dirtiest
        "point_time": latest.get("point_time"),
    }


def get_carbon_index(location_str: str) -> dict | None:
    """
    Full pipeline: location string → geocode → region → signal index.
    Returns None when the location is outside WattTime coverage.
    """
    coords = geocode(location_str)
    if not coords:
        return None
    region = get_region(*coords)
    if not region:
        return None
    return get_signal_index(region)


def main() -> None:
    test_locations = [
        "Washington, US",
        "Texas, US",
        "California, US",
        "Germany, DE",
        "South Korea, KR",
        "Mexico, MX",
    ]
    print(f"{'Location':<25} {'Region':<22} {'Carbon %':>8}  Point time (UTC)")
    print("-" * 80)
    for loc in test_locations:
        time.sleep(1)   # Nominatim rate limit: 1 req/s
        result = get_carbon_index(loc)
        if result:
            print(
                f"{loc:<25} "
                f"{result['region']:<22} "
                f"{result['percent']:>8}  "
                f"{result['point_time']}"
            )
        else:
            print(f"{loc:<25} {'(no coverage)'}")


if __name__ == "__main__":
    main()
