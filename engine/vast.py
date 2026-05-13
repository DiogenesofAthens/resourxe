import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("VAST_API_KEY")
_BASE_URL = "https://cloud.vast.ai/api/v0"


def fetch_instances(limit: int = 50) -> list[dict]:
    """Return available Vast.ai GPU instances ordered by price ascending."""
    if not _API_KEY:
        raise RuntimeError("VAST_API_KEY not set in environment")

    query = {
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "order": [["dph_total", "asc"]],
        "limit": limit,
    }

    resp = requests.get(
        f"{_BASE_URL}/bundles/",
        params={"q": json.dumps(query), "api_key": _API_KEY},
        timeout=15,
    )
    resp.raise_for_status()

    offers = resp.json().get("offers", [])
    return [_normalize(o) for o in offers]


def _normalize(offer: dict) -> dict:
    return {
        "provider": "vast",
        "gpu_model": offer.get("gpu_name", "unknown"),
        "price_per_hour": float(offer.get("dph_total") or 0),
        "available_units": int(offer.get("num_gpus") or 1),
        "location": offer.get("geolocation") or "unknown",
        "reliability": float(offer.get("reliability2") or 0),
        "raw": offer,
    }


def main() -> None:
    instances = fetch_instances(limit=50)
    print(f"Found {len(instances)} available instances\n")
    print(f"{'GPU':<28} {'$/hr':>8}  {'GPUs':>4}  {'Reliability':>11}  Location")
    print("-" * 75)
    for inst in instances[:10]:
        print(
            f"{inst['gpu_model']:<28}"
            f"{inst['price_per_hour']:>8.4f}  "
            f"{inst['available_units']:>4}  "
            f"{inst['reliability']:>11.3f}  "
            f"{inst['location']}"
        )


if __name__ == "__main__":
    main()
