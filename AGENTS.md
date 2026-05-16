# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this project is

ResourXe is a GPU compute routing engine. It queries compute marketplaces and scores results by price and/or carbon intensity to recommend the cheapest or greenest option for a given AI workload.

## Running the code

```bash
# Install dependencies
pip3 install -r requirements.txt

# Start the web app (http://localhost:8000)
python3 app.py

# Smoke-test individual engine modules
python3 engine/vast.py        # top 10 cheapest Vast.ai instances
python3 engine/watttime.py    # carbon index for 6 test locations
python3 engine/scorer.py      # balanced score (default)
python3 engine/scorer.py 0.0  # price only
python3 engine/scorer.py 1.0  # carbon only
```

Python 3.9 is the runtime. All modules use `from __future__ import annotations` where `X | Y` union syntax is needed.

## Architecture

The engine is built as independent provider modules that each expose a normalized record schema, with a scorer layer (not yet built) that combines them.

**Provider record schema** (output of each provider module):
```python
{
  "provider": str,         # e.g. "vast"
  "gpu_model": str,
  "price_per_hour": float,
  "available_units": int,
  "location": str,         # city/country string from provider
  "reliability": float,    # 0–1
  "raw": dict              # full original API response
}
```

**`engine/vast.py`** — Vast.ai integration
- Auth: API key as `?api_key=` query param
- Endpoint: `GET https://cloud.vast.ai/api/v0/bundles/` (note: v0, not v1 — v1 returns 404)
- Filter query passed as JSON-serialized `q` param; filters to rentable+not-rented, orders by `dph_total` asc
- Key raw fields: `gpu_name`, `dph_total`, `num_gpus`, `geolocation`, `reliability2`

**`engine/watttime.py`** — Carbon intensity integration
- Auth: POST `/login` with HTTP Basic → JWT token, cached in-process for 29 min
- Pipeline for a location string: `geocode()` → `get_region()` → `get_signal_index()`
- Geocoding uses OpenStreetMap Nominatim (no key required); respect 1 req/s rate limit
- Region lookup: `GET /v3/region-from-loc` (not `/v3/region` — that path redirects to docs)
- Signal index: `GET /v3/signal-index` returns `value` 0–100 percentile, **lower = cleaner**
- Free tier covers real-time signal index only; historical and raw MOER require paid tier
- Returns `None` for locations outside WattTime coverage (graceful degradation expected)

**`engine/scorer.py`** — combines provider records with carbon data into a ranked list
- Deduplicates locations before hitting Nominatim (avoids redundant API calls and respects rate limit)
- Min-max normalizes price and carbon independently across the result set
- Instances without WattTime coverage get a neutral `carbon_score` of 0.5
- `composite_score = (1 - carbon_weight) * price_score + carbon_weight * carbon_score`
- Exposes `score(instances, carbon_weight)` and `fetch_and_score(limit, carbon_weight)`

**`app.py`** — FastAPI web app (entry point)
- `GET /` — serves `static/index.html`
- `POST /api/query` — accepts `{carbon_weight, limit, top_n}`, returns ranked results (strips `raw` field)
- `GET /api/health` — health check
- Run with `python3 app.py`; hot-reloads on file changes

**`static/index.html`** — single-page frontend (Tailwind CSS via CDN, vanilla JS)
- Slider controls `carbon_weight` 0–1; sends POST to `/api/query`
- Animated loading steps with timed labels that mirror the actual query pipeline duration (~30–40 s)
- Color-coded carbon badge: green &lt;34, yellow 34–66, red &gt;66

## Environment

Copy `.env.example` to `.env`. Required variables:
```
VAST_API_KEY=
WATTTIME_USERNAME=
WATTTIME_PASSWORD=
```
