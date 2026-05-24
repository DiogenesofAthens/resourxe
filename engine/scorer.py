from __future__ import annotations

import os
import sys
import time

# Allow running as a script from the project root or directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import vast, lambda_labs, runpod, watttime


def score(instances: list[dict], carbon_weight: float = 0.5) -> list[dict]:
    """
    Enrich instances with carbon data and return them sorted by composite score.

    carbon_weight: 0.0 = rank by price only, 1.0 = rank by carbon only, 0.5 = balanced.
    Instances without WattTime coverage receive a neutral carbon score of 0.5.
    """
    if not 0.0 <= carbon_weight <= 1.0:
        raise ValueError("carbon_weight must be between 0.0 and 1.0")

    # Deduplicate locations before hitting Nominatim (1 req/s limit)
    unique_locations = {
        inst["location"]
        for inst in instances
        if inst["location"] not in ("unknown", None)
    }

    carbon_map: dict[str, float | None] = {}
    for i, loc in enumerate(unique_locations):
        if i > 0:
            time.sleep(1)  # Nominatim rate limit
        result = watttime.get_carbon_index(loc)
        carbon_map[loc] = result["percent"] if result else None

    for inst in instances:
        carbon = carbon_map.get(inst["location"])
        inst["carbon_index"] = carbon  # 0–100, None if no coverage

    # Min-max normalize price (lower = better)
    prices = [i["price_per_hour"] for i in instances]
    price_min, price_max = min(prices), max(prices)
    price_range = (price_max - price_min) or 1.0

    # Min-max normalize carbon across instances that have coverage
    covered = [i["carbon_index"] for i in instances if i["carbon_index"] is not None]
    if covered:
        c_min, c_max = min(covered), max(covered)
        c_range = (c_max - c_min) or 1.0
    else:
        c_min, c_range = 0.0, 1.0

    price_w = 1.0 - carbon_weight

    for inst in instances:
        inst["price_score"] = (inst["price_per_hour"] - price_min) / price_range

        c = inst["carbon_index"]
        inst["carbon_score"] = 0.5 if c is None else (c - c_min) / c_range

        inst["composite_score"] = (
            price_w * inst["price_score"] + carbon_weight * inst["carbon_score"]
        )

    return sorted(instances, key=lambda x: x["composite_score"])


def fetch_and_score(
    limit: int = 50,
    carbon_weight: float = 0.5,
    providers: list[str] | None = None,
) -> list[dict]:
    """
    Fetch instances from all configured providers, merge, and score.

    providers: restrict to a subset, e.g. ["vast", "lambda", "runpod"].
               None (default) fetches from all available providers.
    """
    if providers is None:
        providers = ["vast", "lambda", "runpod"]

    instances: list[dict] = []
    errors: list[str] = []

    if "vast" in providers:
        try:
            instances.extend(vast.fetch_instances(limit=limit))
        except Exception as exc:
            errors.append(f"vast: {exc}")

    if "lambda" in providers:
        try:
            instances.extend(lambda_labs.fetch_instances(limit=limit))
        except Exception as exc:
            errors.append(f"lambda: {exc}")

    if "runpod" in providers:
        try:
            instances.extend(runpod.fetch_instances(limit=limit))
        except Exception as exc:
            errors.append(f"runpod: {exc}")

    if not instances:
        raise RuntimeError(
            "No instances returned from any provider. Errors: " + "; ".join(errors)
        )

    if errors:
        import logging
        logging.getLogger(__name__).warning(
            "Some providers failed (others succeeded): %s", "; ".join(errors)
        )

    return score(instances, carbon_weight=carbon_weight)


def main() -> None:
    carbon_weight = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print(f"Fetching instances (carbon_weight={carbon_weight})...\n")
    results = fetch_and_score(limit=50, carbon_weight=carbon_weight)

    print(
        f"{'#':<3} {'GPU':<25} {'$/hr':>7}  {'Carbon%':>7}  "
        f"{'P-score':>7}  {'C-score':>7}  {'Score':>7}  Location"
    )
    print("-" * 95)
    for i, inst in enumerate(results[:top_n], 1):
        carbon = (
            f"{inst['carbon_index']:>7.0f}"
            if inst["carbon_index"] is not None
            else "    n/a"
        )
        print(
            f"{i:<3} "
            f"{inst['gpu_model']:<25} "
            f"{inst['price_per_hour']:>7.4f}  "
            f"{carbon}  "
            f"{inst['price_score']:>7.3f}  "
            f"{inst['carbon_score']:>7.3f}  "
            f"{inst['composite_score']:>7.3f}  "
            f"{inst['location']}"
        )


if __name__ == "__main__":
    main()
