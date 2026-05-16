# ResourXe

GPU compute routing engine. Queries cloud GPU marketplaces and scores available instances by price and carbon intensity — find the cheapest compute, the greenest, or any blend in between.

**Live demo:** https://resourxe.vercel.app/ &nbsp;·&nbsp; **GitHub:** https://github.com/DiogenesofAthens/resourxe

---

## How It Works

Each provider integration is an independent Python module that queries its marketplace API and returns a normalized record. A composite scorer ranks results by a configurable weight between pure price minimization (0.0) and pure carbon minimization (1.0).

Current providers:
- **Vast.ai** — GPU cloud marketplace, ordered by hourly price
- **WattTime** — real-time marginal carbon intensity by grid region

---

## Tech Stack

- **Python 3.9** — modular provider architecture
- **Flask** — web application and API
- **Vast.ai API** — GPU instance availability and pricing
- **WattTime API** — real-time grid carbon intensity

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment variables**

```bash
cp .env.example .env   # then fill in your values
```

| Variable | Description |
|---|---|
| `VAST_API_KEY` | Vast.ai API key |
| `WATTTIME_USERNAME` | WattTime account username |
| `WATTTIME_PASSWORD` | WattTime account password |

**3. Run**

```bash
python app.py    # http://localhost:8000
```

---

## Architecture

```
engine/
  vast.py       — Vast.ai integration: queries rentable GPU instances
  watttime.py   — WattTime integration: fetches carbon intensity by location
  scorer.py     — Composite scorer: blends price rank and carbon index
app.py          — Flask web app and API
```

---

## Scorer

```bash
python engine/scorer.py       # balanced score (default weight: 0.5)
python engine/scorer.py 0.0   # price only
python engine/scorer.py 1.0   # carbon only
```

The scorer normalizes each provider's results onto a 0–1 scale for both price rank and carbon index, then computes a weighted average. Results are sorted by composite score ascending.

---

## Provider Record Schema

All provider modules return a normalized record:

```python
{
    "provider":        str,    # e.g. "vast"
    "gpu_model":       str,
    "price_per_hour":  float,
    "available_units": int,
    "location":        str,    # city/country
    "reliability":     float,  # 0–1
    "raw":             dict    # full original API response
}
```
