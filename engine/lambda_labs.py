"""
Lambda Labs GPU cloud integration.

Docs: https://cloud.lambdalabs.com/api/v1/
Auth: HTTP Basic auth — API key as username, empty password.

Returns the normalised provider record schema:
{
    "provider":        str,
    "gpu_model":       str,
    "price_per_hour":  float,
    "available_units": int,
    "location":        str,
    "reliability":     float,   # Lambda Labs doesn't expose this; hardcoded 0.99
    "raw":             dict,
}

Only instance types with capacity available in at least one region are returned.
"""
from __future__ import annotations

import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

_API_KEY  = os.getenv("LAMBDA_LABS_API_KEY")
_BASE_URL = "https://cloud.lambdalabs.com/api/v1"

# Lambda Labs availability isn't tracked per-instance the way Vast.ai is.
# We use 0.99 as a conservative proxy for their SLA-backed infrastructure.
_DEFAULT_RELIABILITY = 0.99


def fetch_instances(limit: int = 50) -> list[dict]:
    """
    Return available Lambda Labs GPU instance types with live pricing.
    Raises RuntimeError if the API key is not set.
    """
    if not _API_KEY:
        raise RuntimeError("LAMBDA_LABS_API_KEY not set in environment")

    resp = requests.get(
        f"{_BASE_URL}/instance-types",
        auth=(_API_KEY, ""),   # Basic auth: key as username, no password
        timeout=15,
    )
    resp.raise_for_status()

    instance_types: dict = resp.json().get("data", {})

    results = []
    for name, entry in instance_types.items():
        regions = entry.get("regions_with_capacity_available", [])
        if not regions:
            continue  # no capacity — skip

        instance_info = entry.get("instance_type", {})
        specs = instance_info.get("specs", {})

        # Primary region for carbon-intensity lookup
        primary_region = regions[0].get("name", "") if regions else ""
        location = _region_to_location(primary_region) or name

        results.append(
            _normalize(
                name=name,
                instance_info=instance_info,
                specs=specs,
                location=location,
                available_units=len(regions),
                raw=entry,
            )
        )
        if len(results) >= limit:
            break

    return sorted(results, key=lambda x: x["price_per_hour"])


def _normalize(
    name: str,
    instance_info: dict,
    specs: dict,
    location: str,
    available_units: int,
    raw: dict,
) -> dict:
    price_cents: Optional[int] = instance_info.get("price_cents_per_hour")
    price = (price_cents / 100.0) if price_cents is not None else 0.0

    gpu_quantity = specs.get("gpus", 1) or 1
    gpu_name = _parse_gpu_name(name, gpu_quantity)

    return {
        "provider":        "lambda",
        "gpu_model":       gpu_name,
        "price_per_hour":  price,
        "available_units": available_units,
        "location":        location,
        "reliability":     _DEFAULT_RELIABILITY,
        "raw":             raw,
    }


def _parse_gpu_name(instance_name: str, gpu_count: int) -> str:
    """
    Derive a human-readable GPU label from the Lambda instance type name.
    Examples:
        gpu_1x_a100          -> "NVIDIA A100 (1x)"
        gpu_8x_h100_sxm5     -> "NVIDIA H100 SXM5 (8x)"
        gpu_1x_a10            -> "NVIDIA A10 (1x)"
    """
    # Strip the leading "gpu_Nx_" prefix
    parts = instance_name.split("_")
    # Find the multiplier part (e.g. "1x", "8x")
    try:
        count_idx = next(i for i, p in enumerate(parts) if p.endswith("x") and p[:-1].isdigit())
        gpu_parts = parts[count_idx + 1 :]
    except StopIteration:
        gpu_parts = parts[1:]

    model = " ".join(p.upper() for p in gpu_parts)
    return f"NVIDIA {model} ({gpu_count}x)"


# Map Lambda Labs region slugs → approximate city/country strings
# for WattTime geo-lookup compatibility.
_REGION_MAP: dict[str, str] = {
    "us-west-1":   "Portland, Oregon, USA",
    "us-west-2":   "Phoenix, Arizona, USA",
    "us-west-3":   "Salt Lake City, Utah, USA",
    "us-south-1":  "Austin, Texas, USA",
    "us-east-1":   "Ashburn, Virginia, USA",
    "us-midwest-1":"Chicago, Illinois, USA",
    "europe-central-1": "Frankfurt, Germany",
    "asia-south-1":     "Mumbai, India",
    "me-west-1":        "Dubai, UAE",
    "australia-southeast-1": "Sydney, Australia",
}


def _region_to_location(region: str) -> Optional[str]:
    return _REGION_MAP.get(region)


def main() -> None:
    instances = fetch_instances(limit=50)
    print(f"Found {len(instances)} available Lambda Labs instance types\n")
    print(f"{'GPU':<35} {'$/hr':>8}  {'Regions':>7}  Location")
    print("-" * 80)
    for inst in instances[:10]:
        print(
            f"{inst['gpu_model']:<35}"
            f"{inst['price_per_hour']:>8.4f}  "
            f"{inst['available_units']:>7}  "
            f"{inst['location']}"
        )


if __name__ == "__main__":
    main()
