# Liner Fleet & Speed Optimizer

Decision-support demo: allocate a shared, homogeneous fleet across weekly liner services and choose
sailing speeds under two directional routing scenarios (mixed routing vs Red Sea disruption / full Cape).
The allocation is solved as an exact 0–1 MILP with Google OR-Tools (SCIP backend).

Services are CMA CGM FAL2, FAL3 and FAL5 (Asia–North Europe) with publicly reported port rotations. Scenarios: **mixed routing**
(westbound Cape, eastbound Suez) vs **full Cape**. Leg distances are derived from authored sea-lane waypoints;
economic inputs are illustrative. Nothing here is CMA CGM operational or financial data (sources in `app/data.py`).

Design specs: `docs/01_optimization_model.md` (model), `docs/02_fullstack_architecture.md` (stack/API/tests),
`docs/03_ui_design.md` (UI).

## Setup (Windows)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app
```

Open http://127.0.0.1:8000. The solver runs fully offline; the map tiles (OpenStreetMap), Leaflet and
Plotly come from CDNs and degrade gracefully without internet.

## Test

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt   # once, for the browser tests
.venv\Scripts\python -m pytest
```

Tests cover the per-option math, the SCIP model (cross-checked against brute-force enumeration),
the independent verifier, the A / B1 / B2 comparison, the routing data (leg distances vs waypoints
and a published reference), the API, and the frontend in headless Chrome (skipped if unavailable).

## How it works

1. `app/modeling.py` — for every service and every fleet size n = 1..F, compute the least-cost speed
   within [v_min, v_max], the sailing time and the weekly cost. These are model coefficients.
2. `app/solver.py` — binary `y[s,n]` for every option; linear constraints C1 one option per service,
   C2 fleet pool, C4+C7 weekly frequency with buffer, C5 speed bounds, C6 fleet cap, C8 max round trip;
   minimize total weekly cost. SCIP decides feasibility; INFEASIBLE results are explained afterwards.
3. `app/verifier.py` — re-derives every constraint and cost from raw inputs; a failing plan is never shown.
4. `app/comparison.py` — A (mixed routing optimal), B1 (full Cape with A's ship counts, speeds
   recomputed; savings only if feasible), B2 (full Cape reoptimized).
5. `app/main.py` — FastAPI: `GET /api/config`, `POST /api/optimize`, `POST /api/compare`, `GET /api/health`.
6. `static/` — vanilla JS app with a sidebar and three pages (Decision Dashboard, Scenario Configuration,
   Model & Methodology), Plotly charts, KaTeX equations, three synchronized Leaflet maps (A / B1 / B2).

## Troubleshooting

- `python` not found: use `py -3.12` or `.venv\Scripts\python` (bare `python` is the Microsoft Store stub).
- Port in use: add `--port 8001`.
