from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from engine import scorer

_HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="ResourXe")

# ---------------------------------------------------------------------------
# Demo dataset — real-world-representative snapshot cached May 2026
# Returned instantly when the client passes demo=true, bypassing live APIs.
# ---------------------------------------------------------------------------
_DEMO_RESULTS = [
    {"provider": "vast", "gpu_model": "RTX 4090",      "price_per_hour": 0.3890, "available_units": 4, "location": "Portland, OR",    "reliability": 0.978, "carbon_index": 12},
    {"provider": "vast", "gpu_model": "H100 SXM5 80GB","price_per_hour": 2.4900, "available_units": 2, "location": "Seattle, WA",     "reliability": 0.995, "carbon_index": 18},
    {"provider": "vast", "gpu_model": "A100 SXM4 80GB","price_per_hour": 1.2200, "available_units": 8, "location": "Montréal, QC",    "reliability": 0.989, "carbon_index": 8 },
    {"provider": "vast", "gpu_model": "RTX 4090",      "price_per_hour": 0.4120, "available_units": 2, "location": "Amsterdam, NL",   "reliability": 0.961, "carbon_index": 41},
    {"provider": "vast", "gpu_model": "A6000",          "price_per_hour": 0.5500, "available_units": 6, "location": "Los Angeles, CA", "reliability": 0.942, "carbon_index": 55},
    {"provider": "vast", "gpu_model": "H100 PCIe 80GB","price_per_hour": 1.9800, "available_units": 4, "location": "Dallas, TX",      "reliability": 0.987, "carbon_index": 72},
    {"provider": "vast", "gpu_model": "RTX 3090",      "price_per_hour": 0.2490, "available_units": 12,"location": "Warsaw, PL",      "reliability": 0.934, "carbon_index": 78},
    {"provider": "vast", "gpu_model": "A100 PCIe 40GB","price_per_hour": 0.7800, "available_units": 3, "location": "Frankfurt, DE",   "reliability": 0.981, "carbon_index": 48},
    {"provider": "vast", "gpu_model": "L40S",           "price_per_hour": 1.0200, "available_units": 8, "location": "Chicago, IL",    "reliability": 0.972, "carbon_index": 60},
    {"provider": "vast", "gpu_model": "RTX 4080",      "price_per_hour": 0.3290, "available_units": 5, "location": "Vancouver, BC",   "reliability": 0.956, "carbon_index": 15},
]


def _score_and_rank_demo(carbon_weight: float, top_n: int) -> dict:
    import copy
    rows = copy.deepcopy(_DEMO_RESULTS)
    prices  = [r["price_per_hour"] for r in rows]
    carbons = [r["carbon_index"]   for r in rows]
    p_min, p_max = min(prices),  max(prices)
    c_min, c_max = min(carbons), max(carbons)
    for r in rows:
        r["price_score"]     = round((r["price_per_hour"] - p_min) / (p_max - p_min) if p_max > p_min else 0.0, 3)
        r["carbon_score"]    = round((r["carbon_index"]   - c_min) / (c_max - c_min) if c_max > c_min else 0.5, 3)
        r["composite_score"] = round((1 - carbon_weight) * r["price_score"] + carbon_weight * r["carbon_score"], 3)
    rows.sort(key=lambda r: r["composite_score"])
    ranked = [{**r, "rank": i + 1} for i, r in enumerate(rows[:top_n])]
    return {"results": ranked, "carbon_weight": carbon_weight, "total_fetched": len(rows), "providers": ["vast"], "demo": True}


class QueryRequest(BaseModel):
    carbon_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=100)
    top_n: int = Field(default=10, ge=1, le=50)
    demo: bool = Field(default=False, description="Return cached demo data instantly (no live API calls)")
    providers: list[str] | None = Field(
        default=None,
        description="Restrict to specific providers: 'vast', 'lambda', 'runpod'. "
                    "Omit to query all configured providers.",
    )


@app.get("/")
def index():
    return FileResponse(os.path.join(_HERE, "static", "index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def query(req: QueryRequest):
    if req.demo:
        return _score_and_rank_demo(req.carbon_weight, req.top_n)

    try:
        results = scorer.fetch_and_score(
            limit=req.limit,
            carbon_weight=req.carbon_weight,
            providers=req.providers,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    clean = []
    for r in results[: req.top_n]:
        clean.append(
            {
                "rank": len(clean) + 1,
                "provider": r["provider"],
                "gpu_model": r["gpu_model"],
                "price_per_hour": r["price_per_hour"],
                "available_units": r["available_units"],
                "location": r["location"],
                "reliability": round(r["reliability"], 3),
                "carbon_index": r["carbon_index"],
                "price_score": round(r["price_score"], 3),
                "carbon_score": round(r["carbon_score"], 3),
                "composite_score": round(r["composite_score"], 3),
            }
        )

    providers_seen = sorted({r["provider"] for r in results})

    return {
        "results": clean,
        "carbon_weight": req.carbon_weight,
        "total_fetched": len(results),
        "providers": providers_seen,
        "demo": False,
    }


app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
