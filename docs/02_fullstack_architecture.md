# 02 — Full-stack Technical Architecture & OR-Tools Implementation

**Objective:** Build a reliable **local-first** interactive decision-support demo with a Python mathematical model and a real Google OR-Tools optimization solve, not pre-scripted results.

Read `01_optimization_model.md` FIRST for business definitions, exact formulas, constraints, assumptions, and comparison logic. Read `03_ui_design.md` for user-facing requirements.

## 1. Stack

- **Backend:** Python 3.12; FastAPI + Pydantic v2; Uvicorn.
- **Optimization:** Google OR-Tools linear solver wrapper `ortools.linear_solver.pywraplp` with the **SCIP** backend (bundled in the `ortools` pip wheel), solving the 0–1 MILP of `01` §6 with binary option-selection variables and floating-point costs.
- **Frontend:** vanilla HTML5 + CSS3 + vanilla ES modules JS. No React, no node build.
- **Charts:** Plotly.js via jsDelivr CDN (`plotly.js-dist-min@2.35.2`).
- **Equations:** KaTeX via jsDelivr (`katex@0.16.11`); plain-text fallbacks stay visible offline.
- **Map:** Leaflet.js with OSM tiles when online; a fallback message offline. Authored directional waypoints with named port calls. **No real-time AIS**.
- **Data:** default parameters, services (CMA CGM FAL2, FAL3, FAL5), port rotations, directional waypoints and sources in `app/data.py`; leg distances derived from the waypoints; no DB.
- **Browser tests:** Playwright (dev dependency, `requirements-dev.txt`) driving the installed Chrome.
- **Runtime:** project venv at `.venv/` (`py -3.12 -m venv .venv`), then `uvicorn app.main:app` → `http://127.0.0.1:8000`.

The core solve must work without internet. CDNs and map tiles must degrade gracefully.

## 2. Project layout (repo root = `demo_fleet_allocation/`)

```text
demo_fleet_allocation/
├── 01_optimization_model.md
├── 02_fullstack_architecture.md
├── 03_ui_design.md
├── README.md
├── requirements.txt
├── requirements-dev.txt     # playwright (browser tests)
├── pytest.ini
├── app/
│   ├── __init__.py
│   ├── data.py              # scenarios (directional routing), rotations, waypoints, defaults, sources
│   ├── schemas.py           # Pydantic request models + cross-field validation (responses are dicts built in main.py)
│   ├── modeling.py          # per-option coefficients; polyline distance; round trip = sum of legs
│   ├── solver.py            # OR-Tools pywraplp/SCIP 0-1 MILP
│   ├── verifier.py          # independent constraint/cost checks of a solution
│   ├── comparison.py        # A vs B1 (b_fixed) vs B2 (b)
│   └── main.py              # FastAPI routes + static mount
├── static/
│   ├── index.html           # single page, sidebar + 3 pages: Model, Inputs, Results
│   ├── css/styles.css
│   └── js/
│       ├── app.js           # shared state, page switching, inputs, /api/compare, results, stale handling
│       ├── charts.js        # allocation, speed and cost-breakdown charts (A/B1/B2)
│       └── map.js           # three synchronized scenario maps (A/B1/B2), one clock, service filter
└── tests/
    ├── test_modeling.py
    ├── test_solver.py
    ├── test_verifier.py
    ├── test_comparison.py
    ├── test_data.py         # directional routing, leg distances vs waypoints and published reference
    ├── test_api.py          # also covers main.py and schemas.py
    └── test_ui.py           # static/ frontend via Playwright + Chrome (skipped if unavailable)
```

Test-file mapping: one test file per logic module; `schemas.py` and `main.py` are tested through `test_api.py`; the frontend through `test_ui.py`.

## 3. Request / response contracts

### `GET /api/config`

Returns the **complete default request payload** (fleet, vessel, economics, services with directional legs, rules), scenario metadata including each scenario's `routing` (`{westbound, eastbound}` → `cape`/`suez`), input bounds, directional map waypoints with named ports (`routes`), `service_meta`, and disclaimers/data sources. The frontend initializes all inputs from this; defaults live **only** in `app/data.py`.

### `POST /api/optimize`

Runs one scenario: validate input → compute per-option coefficients → build/solve SCIP model → verify independently (or explain infeasibility) → return results.

Example request (abbreviated; defaults come from `/api/config`):

```json
{
  "scenario": "mixed_routing",
  "fleet": {
    "available_vessels": 44,
    "min_speed_knots": 12,
    "max_speed_knots": 22,
    "reference_speed_knots": 18,
    "reference_fuel_tonnes_per_day": 100
  },
  "economics": {
    "fuel_price_usd_per_tonne": 600,
    "deployment_cost_usd_per_vessel_week": 150000
  },
  "services": [
    {
      "service_id": "FAL2",
      "name": "FAL2 · French Asia Line 2 (North China – North Europe)",
      "legs": {
        "westbound": {"cape": 15138},
        "eastbound": {"suez": 11825, "cape": 15532}
      },
      "port_days": 10
    }
  ],
  "rules": {
    "max_fleet_per_service": {"enabled": false, "limits": {"FAL2": 15}},
    "minimum_schedule_buffer": {"enabled": true, "days_by_service": {"FAL2": 2}},
    "maximum_round_trip_time": {"enabled": false, "days_by_service": {"FAL2": 105}}
  }
}
```

**Validation (server-side):**
- Pydantic types; `available_vessels` integer ≥ 1; fuel price > 0; incremental vessel operating cost ≥ 0; leg distances within bounds; port days ≥ 0; reference speed/fuel > 0.
- `0 < min_speed_knots ≤ max_speed_knots` (plus a documented sane upper bound, e.g. ≤ 30).
- 1–6 services, unique `service_id`s; each service must provide every leg variant any scenario uses (westbound `cape`, eastbound `suez` and `cape`).
- Each **enabled** rule must provide a value for every service id and no unknown ids; caps integer ≥ 1, buffer ≥ 0, Tmax > 0.
- Violations return 422 with a field-level message.

Successful response shape (keys only; `null`s are documentation placeholders):

```json
{
  "scenario": "mixed_routing",
  "status": "OPTIMAL",
  "solver": "ORTOOLS_SCIP",
  "solve_time_ms": null,
  "model_size": {"binary_variables": null, "constraints": null},
  "objective_usd_week": null,
  "metrics": {
    "total_cost_usd_week": null,
    "fuel_cost_usd_week": null,
    "deployment_cost_usd_week": null,
    "allocated_vessels": null,
    "available_vessels": null,
    "idle_vessels": null
  },
  "services": [
    {
      "service_id": "FAL2",
      "selected_vessels": null,
      "speed_knots": null,
      "speed_binding": "frequency | min_speed | max_cycle",
      "sailing_days": null,
      "active_cycle_days": null,
      "scheduled_rotation_days": null,
      "slack_days": null,
      "fuel_tonnes_week": null,
      "fuel_cost_usd_week": null,
      "deployment_cost_usd_week": null,
      "total_cost_usd_week": null
    }
  ],
  "verification": {"passed": true, "violations": []},
  "metadata": {"estimated_inputs": true}
}
```

For infeasible runs (status decided by SCIP): `status: "INFEASIBLE"`, a human-readable `reason`, `diagnostics` = `{min_vessels_by_service, total_min_vessels, available_vessels, reasons[]}` computed after the solve (per service: minimum vessels satisfying C4/C7/C8, or `null` plus the reason when no fleet size works; C6 caps below that minimum; sum of minimums vs `F`), and **no** `metrics`/`services` solution fields.

### `POST /api/compare`

Same body as `/api/optimize` without `scenario`. Solves A (`mixed_routing`) and B2 (`full_cape`) independently, then evaluates B1 (A's counts, speeds recomputed under full Cape with all active rules). API keys stay `a`, `b`, `b_fixed`; the UI presents them as A, B2, B1 in the order A, B1, B2. Response: `a`, `b` (each an `/api/optimize`-shaped result), `b_fixed` (`{feasible, reasons[], allocation}` plus `metrics`/`services` when feasible or `speeds_required_knots` when not; `null` if A has no solution), `disruption_impact_usd_week` (B2 − A), `disruption_impact_pct`, `fixed_fleet_impact_usd_week` (B1 − A, `null` if B1 infeasible), `reoptimization_savings_usd_week` (B1 − B2), `fleet_moves` (B2 − A = B2 − B1 vessels per service). All differences are computed in `comparison.py`; the frontend only displays them. When B1 is infeasible, `reoptimization_savings_usd_week = null`.

### Static frontend

Served from `static/` at `/` with `Cache-Control: no-cache` (always revalidated), so browsers never run stale CSS/JS after an update.

### `GET /api/health`

Health/version probe.

## 4. Optimization steps (required)

1. Compute `D_s` = westbound leg + eastbound leg of the scenario's route variants (`schemas.to_problem` → `modeling.scenario_round_trip_nm`), read `P_s` for each service, and global `F`, `v_min`, `v_max`, `p`, `h`; derive `c = f_ref/(24 v_ref³)`.
2. For every service and every `n` from 1 to `F` (no pre-filtering), compute the option coefficients of `01` §5: `v_opt` (clamped to `[v_min, v_max]`, `+∞` requirements capped at `v_max`), `sail`, fuel, deployment and total cost, at full precision. This step makes no feasibility decision.
3. Build the pywraplp/SCIP model with all options: `y[s,n]` BoolVars; C1, C2, C4(+C7), C5 rows always; C6 and C8 rows when enabled; minimize Σ C·y (`01` §6).
4. Solve with a time limit (10 s); return actual status and wall time. FEASIBLE-not-OPTIMAL is reported truthfully.
5. If INFEASIBLE: compute the post-solve diagnostics (`01` §6) to explain it; return no solution.
6. Otherwise read `y` with `solution_value() > 0.5`; independently verify against the original formulas (`verifier.py`); if verification fails, return a 500-class error, never the solution.
7. Serialize.

**Important:** the solver makes the discrete fleet allocation decision and enforces every rule; the speed of each option is precomputed input data (least-cost speed for that fleet size). Do **not** claim the solver searches continuous speeds.

### Solver sketch

```python
from ortools.linear_solver import pywraplp

solver = pywraplp.Solver.CreateSolver("SCIP")
if solver is None:
    raise RuntimeError("SCIP backend unavailable in this OR-Tools build")

y = {(s, n): solver.BoolVar(f"y_{s}_{n}") for s, opts in options.items() for n in opts}

# options[s][n] holds the precomputed coefficients of option (s, n): v_opt, sail, cost
for s, opts in options.items():
    solver.Add(sum(y[s, n] for n in opts) == 1)                                    # C1
    solver.Add(sum((o.sail + P[s] + B_eff[s] - 7 * n) * y[s, n]
                   for n, o in opts.items()) <= TOL)                               # C4 + C7
    v_sel = sum(o.v_opt * y[s, n] for n, o in opts.items())
    solver.Add(v_sel >= v_min); solver.Add(v_sel <= v_max)                         # C5 (non-binding, visible)
    if s in caps:
        solver.Add(sum(n * y[s, n] for n in opts) <= caps[s])                      # C6
    if s in tmax:
        solver.Add(sum(o.sail * y[s, n] for n, o in opts.items()) + P[s] <= tmax[s] + TOL)  # C8
solver.Add(sum(n * y[s, n] for s, opts in options.items() for n in opts) <= fleet)  # C2

solver.Minimize(sum(opt.cost * y[s, n] for s, opts in options.items() for n, opt in opts.items()))
solver.SetTimeLimit(10_000)
status = solver.Solve()
```

**Why SCIP rather than CP-SAT:** the problem is a textbook 0–1 MILP; SCIP takes the floating-point costs directly (no integer scaling/rounding error to explain), reports a standard MILP status, and the formulation reads naturally as a standard OR model. CP-SAT would also work but needs cost scaling.

## 5. Frontend ↔ Backend lifecycle

1. Page loads `GET /api/config` and populates one in-memory state object shared by the three pages.
0. On page load the app runs `/api/compare` on the defaults, so the Decision Dashboard opens on real results.
2. Operator edits inputs on **Scenario Configuration**. Any edit marks displayed results **stale** (sidebar badge, faded results, banner).
3. Operator clicks **Run Scenario Comparison** (the single primary action) → `POST /api/compare`.
4. Disable the action, show loading, `fetch` with JSON body and timeout.
5. On success, store the inputs snapshot of this run, navigate to the **Decision Dashboard** and replace (never merge) all sections and the three maps.
6. 422 → validation messages on the Inputs page and results cleared; 5xx → safe technical failure; infeasible cases → dedicated explanatory state, never a stale result.
7. Map resized when the Results page becomes visible; animation paused on leaving the page; `prefers-reduced-motion` respected.

`POST /api/optimize` (single scenario) remains available in the API but is not used by the UI.

## 6. Vessel map animation

The map is a presentation layer for synthetic *steady-state* fleet trajectories (`01` §9).

- Three maps (Baseline, Unchanged Fleet, Optimized Fleet = A, B1, B2) side by side, driven by `MapSync`: one synthetic clock and one set of controls; service checkboxes (any combination, All/Clear) that only toggle layers; route click highlights a service on all maps; synchronized pan/zoom and a shared Asia–Europe overview with Suez/Cape labels; port names on hover (all from zoom 5); per-map header with vessels and speeds (single service: vessels, speed, active cycle). Inputs: the case's `selected_vessels`, `speed_knots`, `sailing_days`, `active_cycle_days`, `scheduled_rotation_days`, and the scenario's westbound and eastbound waypoint paths.
- Solid polyline = westbound, dashed = eastbound, faint dotted = the unused route variant; one color per service; named port markers with labels.
- Ship timeline: westbound then eastbound path; sailing time proportional to segment length; equal dwell at each named port; slack at the origin. 7-day spacing between ships.
- Infeasible case: routes drawn, no ships, explanatory overlay.
- Playback rate (1/2/5/10 synthetic days per second) does **not** alter optimized speeds or costs. Pause/reset/scrub; reduced-motion fallback.
- Offline: fallback message; results remain complete.

## 7. Testing and validation

- **test_modeling:** `c` derivation; `v_opt` at frequency-binding / `v_min` plateau / C8-binding; effective buffer zero when C7 off; required speed > v_max capped at v_max (sail too long for C4); `7n ≤ P_s + B_eff` and `Tmax ≤ P_s` handled without division errors; cost formula; high/low fuel price; post-solve diagnostics (minimum fleet per service, reasons).
- **test_solver:** one option per service; Σn ≤ F; options needing speed > v_max never selected (C4); C6 caps and C8 change the solution; SCIP optimum equals exhaustive enumeration over small instances; SCIP returns INFEASIBLE for too-small fleet / impossible Tmax; exactly-v_max option accepted (tolerance); status mapping.
- **test_verifier:** passes a correct solution; flags each type of violation (fleet over F, speed out of bounds, frequency, buffer, cap, Tmax, cost mismatch).
- **test_comparison:** B1 − A field and the identity (B1−A) − (B1−B2) = B2−A; scenario inputs differ; B1 recomputes speeds; B1 feasible vs infeasible; no savings when infeasible; A infeasible case.
- **test_data:** scenario routing per direction; default legs equal waypoint lengths; waypoint geometry within 5% of the published Shanghai–Rotterdam distances; round trip = sum of legs; eastbound starts at the westbound turnaround and is not a reversal; Suez variants pass Suez, Cape variants round Africa; port days = calls × days per call.
- **test_ui:** dashboard is the landing page and auto-runs; sections in decision order; Model & Methodology statement; three synchronized maps (viewport, service filter keeps the clock); three pages; inputs grouped (directional column groups, calculated round trip); comparison shows A/B1/B2 cards, decision summary with the three comparisons, target allocation change table; map service toggles and overview; input change marks results stale and rerun clears it; infeasible B1 shown as INFEASIBLE with no savings; validation error clears results; no JavaScript errors.
- **test_api:** `/api/config` defaults are valid and solve; 422 for negative inputs, `min_speed > max_speed`, duplicate service ids, missing leg variants, missing rule values; malformed JSON; infeasible response has no solution metrics; re-run after toggles changes results; scenario uses the sum of its directional legs.
- **Invariants:** `abs(Σ service totals − total) < 1e-6`, `Σn ≤ F`, `slack ≥ B_eff`, objective recomputed independently.

