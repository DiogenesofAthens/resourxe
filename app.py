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


class QueryRequest(BaseModel):
    carbon_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=100)
    top_n: int = Field(default=10, ge=1, le=50)
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
    }


app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
