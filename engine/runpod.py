"""
RunPod GPU cloud integration.

Docs: https://docs.runpod.io/sdks/graphql/overview
Auth: API key passed as query param: ?api_key=<key>

RunPod exposes two pricing tiers per GPU type:
  - On-demand (secure cloud):  uninterruptablePrice (USD/hr)
  - Spot (community cloud):    minimumBidPrice (USD/hr, interruptible)

We report the on-demand price as price_per_hour so it's comparable across
providers. The spot price is preserved in `raw`.

Returns the normalised provider record schema:
{
    "provider":        str,
    "gpu_model":       str,
    "price_per_hour":  float,
    "available_units": int,
    "location":        str,   # RunPod doesn't expose per-instance location;
    "reliability":     float, #   we use "Distributed / USA" as a proxy.
    "raw":             dict,
}
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_API_KEY  = os.getenv("RUNPOD_API_KEY")
_GQL_URL  = "https://api.runpod.io/graphql"

# RunPod's community cloud spans many geos; we use a US proxy for WattTime.
_DEFAULT_LOCATION    = "Ashburn, Virginia, USA"
_DEFAULT_RELIABILITY = 0.90   # community cloud is interruptible; lower proxy


_GPU_TYPES_QUERY = """
query GpuTypes {
  gpuTypes {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    lowestPrice {
      minimumBidPrice
      uninterruptablePrice
    }
    secureSpotPrice
    communitySpotPrice
  }
}
"""


def fetch_instances(limit: int = 50) -> list[dict]:
    """
    Return available RunPod GPU types with on-demand pricing.
    Types with no reported price are skipped.
    """
    if not _API_KEY:
        raise RuntimeError("RUNPOD_API_KEY not set in environment")

    resp = requests.post(
        _GQL_URL,
        params={"api_key": _API_KEY},
        json={"query": _GPU_TYPES_QUERY},
        timeout=20,
    )
    resp.raise_for_status()

    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"RunPod GraphQL error: {data['errors']}")

    gpu_types: list[dict] = data.get("data", {}).get("gpuTypes", [])

    results = []
    for gpu in gpu_types:
        lowest = gpu.get("lowestPrice") or {}
        price = lowest.get("uninterruptablePrice")  # on-demand USD/hr

        if price is None:
            # Fall back to spot price if on-demand isn't listed
            price = lowest.get("minimumBidPrice")
        if price is None:
            continue   # no pricing data at all

        results.append(_normalize(gpu, float(price)))
        if len(results) >= limit:
            break

    return sorted(results, key=lambda x: x["price_per_hour"])


def _normalize(gpu: dict, price: float) -> dict:
    display_name = gpu.get("displayName") or gpu.get("id", "unknown")
    memory_gb    = gpu.get("memoryInGb")
    label = f"{display_name}" + (f" ({memory_gb}GB)" if memory_gb else "")

    # RunPod doesn't expose available unit counts via the public GQL endpoint
    available_units = 1  # placeholder

    return {
        "provider":        "runpod",
        "gpu_model":       label,
        "price_per_hour":  price,
        "available_units": available_units,
        "location":        _DEFAULT_LOCATION,
        "reliability":     _DEFAULT_RELIABILITY,
        "raw":             gpu,
    }


def main() -> None:
    instances = fetch_instances(limit=50)
    print(f"Found {len(instances)} available RunPod GPU types\n")
    print(f"{'GPU':<35} {'$/hr (on-demand)':>18}  Location")
    print("-" * 75)
    for inst in instances[:10]:
        print(
            f"{inst['gpu_model']:<35}"
            f"{inst['price_per_hour']:>18.4f}  "
            f"{inst['location']}"
        )


if __name__ == "__main__":
    main()
