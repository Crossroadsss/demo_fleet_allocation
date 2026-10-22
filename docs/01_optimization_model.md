# 01 — Optimization Model & Red Sea Scenario Story

**Project:** Liner Fleet Allocation & Sailing Speed Decision Support (demo prototype)  
**Audience:** OR engineers and developers  
**Status:** Implementation specification; do not present numerical results as verified until solver/tests run.  
**Model scope:** a small set of liner services (default 3: CMA CGM FAL2, FAL3, FAL5 — representative Asia–North Europe loops; schema allows 1–6), a shared available fleet of homogeneous, company-owned vessels (default 50, an illustrative shared pool; for reference, the vessels published for these loops under full Cape routing sum to 44 = 14 + 15 + 15; treating them as one homogeneous, jointly allocatable fleet is an illustrative modeling assumption, not a claim about CMA CGM's actual vessel ownership or deployment flexibility), weekly departures, steady-state tactical allocation.

## 1. Product question and storyline

**Business question:** How should a shipping operator allocate a limited fleet across several weekly liner services and adjust sailing speeds when Red Sea/Suez routing changes, while minimizing fuel and incremental vessel operating costs?

Two **hypothetical** routing scenarios with **asymmetric, directional routing** (westbound = Asia → Europe, eastbound = Europe → Asia), solved with the same model and parameters except the route inputs:

1. **Mixed routing (baseline), id `mixed_routing`:** westbound via the Cape of Good Hope, eastbound via Suez / Red Sea.
2. **Red Sea disruption (full Cape), id `full_cape`:** westbound and eastbound via the Cape of Good Hope.

These are illustrative planning assumptions, not claims about CMA CGM's actual current routing practices (public reports of eastbound Suez returns in 2026 are cited as context in `app/data.py`).

**Directional distances:** each service stores leg distances per direction and route variant: westbound via Cape, eastbound via Suez, eastbound via Cape. A scenario selects one variant per direction and `D_s = D_s^westbound + D_s^eastbound`. Default leg distances are **not typed in**: they are the great-circle lengths of authored sea-lane waypoints through the named ports of each real rotation (the same paths the map draws), and the waypoint geometry is checked in tests against a published Shanghai–Rotterdam distance (~10,600 nm via Suez, ~13,800 nm via Cape, ±5%). Port time `P_s` = number of port calls in the loop × 1.5 days (illustrative assumption for large vessels at major hubs).

**Input data and provenance:** Every model parameter (fleet size, vessel fuel curve, speeds, prices, costs, per-service distances and port times) is an **operator-editable input** with a default value. Service names and port rotations are real, publicly reported CMA CGM services; sources are recorded in `app/data.py` (`SOURCES`). Defaults are still **estimates from public information, not CMA CGM operational data**, and the UI must say so. These are scenario assumptions, **not a verified current status of the Red Sea**. Never claim that distances, port times, fuel coefficients, costs, ship positions, or results are actual CMA CGM data.

**Narrative:** Disruption → longer route/time → tension between more vessels and faster sailing to preserve weekly departures → solve constrained fleet allocation → compare cost, speed and fleet changes → evaluate value (and feasibility) of reoptimization.

## 2. Important distinctions

- **Weekly service frequency:** a departure every 7 days for each service; determines how many ships are needed to sustain the rotation.
- **Round-trip sailing/port cycle:** ship's travel plus operating time around its whole service loop.
- **OD cargo transit time:** from cargo origin port to destination port; **not included as a constraint in MVP**. Do not label maximum round-trip time as cargo transit time.
- **Slack:** unused time in the scheduled 7n-day vessel rotation, needed for operational buffering/layover. Minimum Schedule Buffer (C7) is optional.
- **Ship identities and inter-service repositioning:** not modeled. Solutions are steady-state target allocations; no claim about instantaneous feasible ship transfers.

## 3. Indices and parameters

| Symbol | Meaning | Unit | Scope |
|---|---|---|---|
| `s ∈ S` | service (default 3 services) | — | — |
| `n ∈ N_s` | option: integer number of assigned vessels, `N_s = {1,…,F}` | vessels | per service |
| `F` | total vessels available across services (default 50) | vessels | global |
| `D_s` | round-trip **sailing** distance = westbound leg + eastbound leg of the scenario's route variants | nautical miles | per service, per scenario |
| `P_s` | total port stay per loop (excluding buffer); same in both scenarios | days | per service |
| `v_min`, `v_max` | operating speed bounds, editable (default 12 / 22), always enforced | knots | global |
| `p` | bunker fuel price | USD/tonne | global |
| `v_ref`, `f_ref` | reference speed and daily main-engine fuel at that speed | knots, tonnes/day | global (homogeneous fleet) |
| `c` | derived fuel coefficient: per-nautical-mile fuel is `c·v²` | tonnes/(nm·kn²) | global |
| `h` | **incremental vessel operating cost**: `h_active − h_idle`, excluding fuel | USD/vessel/week | global |
| `B_s` | minimum rotation schedule buffer (C7) | days | per service |
| `Tmax_s` | maximum round-trip active cycle time (C8) | days | per service |
| `M_s` | maximum fleet assigned to a service (C6) | vessels | per service |

**Homogeneous fleet:** all vessels share one fuel curve and one incremental operating cost, so `c` and `h` are global (no per-service `c_s`/`h_s` in v1).

**Fuel coefficient from reference consumption:** public sources usually quote daily fuel at a reference speed, so the operator enters `v_ref` and `f_ref` and the model derives

`c = f_ref / (24 · v_ref³)`

so that daily fuel at speed `v` is `f_ref·(v/v_ref)³` and per-nm fuel is `c·v²`.

All monetary quantities are comparable **per week**. Because service departure headway is seven days, **one complete circuit departs per service per week** in steady state; weekly main-propulsion fuel consumption for a service is `c·D_s·v_s²` tonnes. Do **not** multiply this voyage fuel by `n_s` again. If fuel-at-port is later modeled, add it explicitly; do not silently hide it in `c`.

**Cost accounting (owned fleet):** the vessels are company-owned. `h` (API field `deployment_cost_usd_per_vessel_week`, UI label **Incremental Vessel Operating Cost**) is the incremental operating or opportunity cost of deploying an owned vessel compared with leaving it idle, excluding fuel: extra maintenance, consumables, operating expenses, and the opportunity cost of using the vessel rather than keeping it in reserve. With `h = h_active − h_idle`, the unavoidable fixed ownership cost (`F·h_idle` plus capital cost) is the same for every allocation, so it is excluded from the objective without changing the optimum. `h` is not acquisition cost, depreciation, unavoidable ownership cost or charter hire. Default economic values are illustrative, not CMA CGM financial data.

## 4. Primary business variables and solver variables

Business-level decision `x_s`: integer fleet count assigned to service `s`.

The solver uses a **0–1 MILP with multiple-choice binary option variables**:

`y[s,n] = 1` if service `s` is assigned exactly `n` vessels; `0` otherwise.

Recover deployment: `x_s = Σ_(n∈N_s) n*y[s,n]`.

This is an **exact discrete reformulation** of the current homogeneous, uniform-speed, fixed-frequency model over all enumerated feasible integer fleet counts, **not an approximate speed grid search**.

## 5. Per-option preprocessing: speed, times and cost (model input data)

Speed enters the model nonlinearly (`v²` in fuel, `1/v` in sailing time), so it is **not** a solver variable. Instead, for every option `(s,n)` with `n = 1…F`, Python computes the option's speed, sailing time and cost as constants; these are the input coefficients of the linear 0–1 model in §6. **This preprocessing decides nothing about feasibility — the solver does (§6).**

**Effective buffer:** `B_eff_s = B_s` if C7 is enabled, else `0`.

Given `n` vessels on service `s`, uniform average speed `v`, weekly frequency including the effective buffer requires:

`D_s/(24 v) + P_s + B_eff_s ≤ 7 n`.

This induces the minimum frequency speed:

`v_freq(s,n) = D_s / [24(7n − P_s − B_eff_s)]` if `7n − P_s − B_eff_s > 0`, else `+∞` (no speed can meet it; check the denominator before dividing).

Optional maximum active round-trip time `Tmax_s` (C8) requires `D_s/(24 v) + P_s ≤ Tmax_s` and induces:

`v_cycle(s) = D_s/[24(Tmax_s − P_s)]` if `Tmax_s − P_s > 0`, else `+∞`. Ignored (treated as 0) when C8 is disabled.

**Option speed** — the cheapest speed for this option, kept within the speed bounds:

`v_opt(s,n) = min(v_max, max(v_min, v_freq(s,n), v_cycle(s)))`.

If the required speed exceeds `v_max`, `v_opt` is capped at `v_max`; the resulting sailing time is then too long, and the solver's time constraints (C4/C7, C8) reject the option. For every option the solver can select, `v_opt` is the least-cost feasible speed **under the current objective and assumptions**: fuel per voyage strictly increases with speed, no revenue/transit-time utility is optimized, and extra fixed time is allowed as schedule slack.

Per-option coefficients (all at full precision):

- `sail(s,n) = D_s/(24*v_opt)` — sailing days.
- `active_cycle_days(s,n) = sail + P_s`.
- `rotation_days(s,n) = 7n`.
- `slack_days(s,n) = rotation_days − active_cycle_days` (≥ `B_eff_s` for any option satisfying C4/C7).
- `fuel_tonnes_per_week(s,n) = c*D_s*v_opt²`.
- `fuel_usd_per_week(s,n) = p * fuel_tonnes_per_week`.
- `deploy_usd_per_week(s,n) = h*n`.
- `C[s,n] = fuel_usd_per_week + deploy_usd_per_week`.

Numerical caution: do not round speeds before computing costs; round only for display. Use a small tolerance (e.g. `1e-9` days) in the time constraints so an option sailing at exactly `v_max` is not rejected by floating-point error.

## 6. Exact 0–1 MILP formulation

**Objective:**

`min Z = Σ_s Σ_(n∈N_s) C[s,n] * y[s,n]`.

All options `n = 1…F` of every service enter the model (no pre-filtering); every rule is a linear constraint over `y` using the §5 coefficients.

**Always-on constraints:**

- **C1, select one option per service:** `Σ_n y[s,n] = 1`, every service `s`.
- **C2, finite pooled fleet:** `Σ_s Σ_n n*y[s,n] ≤ F`.
- **C3, domain:** `y[s,n] ∈ {0,1}`.
- **C4, weekly frequency (with effective buffer, so it also covers C7):** `Σ_n (sail(s,n) + P_s + B_eff_s − 7n)*y[s,n] ≤ 0`, every `s`.
- **C5, operational speed range:** `v_min ≤ Σ_n v_opt(s,n)*y[s,n] ≤ v_max`, every `s`. Satisfied by construction because `v_opt` is clamped into the bounds; kept as explicit rows so the rule is visible in the model (it never binds).

**Operator-selectable constraints:**

- **C6, maximum fleet per service:** `Σ_n n*y[s,n] ≤ M_s`.
- **C7, minimum schedule buffer:** enters C4 through `B_eff_s` (and through `v_opt`).
- **C8, maximum round-trip active cycle:** `Σ_n sail(s,n)*y[s,n] + P_s ≤ Tmax_s`, every `s`.

**Why the aggregated rows are exact:** C1 forces exactly one `y[s,n] = 1` per service, so each `Σ_n coef(s,n)*y[s,n]` equals the selected option's coefficient — no cancellation between options is possible.

**How infeasible options are excluded:** an option whose required speed exceeds `v_max` (or has no valid speed) sails at the capped `v_max`, so its `sail` is too long and it violates C4 or C8; the solver cannot select it. The solver therefore decides all feasibility, including the scenario-level INFEASIBLE status.

**Post-solve diagnostics (explanation only, not a decision):** when the solver returns INFEASIBLE, Python explains why from the same coefficients: per service, the smallest `n` satisfying C4/C7/C8 (or "none" with the reason, e.g. `Tmax_s ≤ P_s` or C8 needs speed > `v_max`), C6 caps below that minimum, and the sum of minimum fleets versus `F`.

**Solver:** Google OR-Tools linear solver wrapper (`pywraplp`) with the **SCIP** backend. SCIP accepts floating-point coefficients, so costs and times are used at full precision with **no integer scaling**. Results are cross-checked by exhaustive enumeration in tests (feasible for the demo's size). About `|S|·F` binaries (150 for 3 services and 50 vessels).

**Why not let the solver choose speed:** with `v` as a variable the model becomes a MINLP (`v²` objective, bilinear frequency constraint). That needs a nonlinear solver interface (e.g. PySCIPOpt) or a piecewise-linear approximation of `v²`. Enumerating the integer fleet count makes speed a per-option constant, keeping the model an **exact linear 0–1 MILP**.

**Solver statuses (pywraplp):** OPTIMAL, FEASIBLE, INFEASIBLE, UNBOUNDED, ABNORMAL, NOT_SOLVED, MODEL_INVALID. NEVER display a stale solution as though it applies to an infeasible scenario.

## 7. What operator can control

**Inputs (Scenario Configuration page):** available fleet `F`, `v_min`, `v_max` (validated `0 < v_min ≤ v_max`), reference speed and daily fuel (`v_ref`, `f_ref`), bunker price `p`, incremental vessel operating cost `h`, per-service name, directional leg distances and port days, and optional rule toggles/limits C6–C8. Both scenarios are always run together (comparison).

**Core rules C1–C5 are always enforced.** All inputs are validated server-side. For operator-facing labels use `Maximum Round-trip Time`, **not** `Cargo Transit Time`.

## 8. Comparative analytics: 3 analytical states within 2 scenarios

Run both scenarios with common model, common economic inputs, common resource pool:

Presented in UI order **A, B1, B2** (API keys `a`, `b_fixed`, `b`):

- **A — Mixed routing optimal:** optimize under `mixed_routing` → `(x_A*, v_A*, Cost_A*)`.
- **B1 (`b_fixed`) — Full Cape, no fleet reallocation:** keep **A's fleet counts** fixed and recompute each service's option coefficients (`v_opt`, `sail`, cost) under B with all active rules; evaluate B cost **only if** every service's option satisfies the same C4/C7/C8 conditions the solver enforces (C2/C6 hold because A satisfied them with identical counts and parameters). No solver needed: it is a direct evaluation of one fixed option per service.
- **B2 (`b`) — Full Cape reoptimized:** optimize under `full_cape` → `(x_B*, v_B*, Cost_B*)`.

Metrics:

- **Disruption effect with fleet unchanged** (A → B1) `Cost(B1) − Cost(A)`, only if B1 feasible.
- **Optimized disruption cost impact** (A → B2) `Cost(B2) − Cost(A)`.
- **Potential steady-state reoptimization savings** (B1 → B2) `Cost(B1) − Cost(B2)`, **only if B1 feasible**; not transition-adjusted and not guaranteed cash savings.
- When B1 is infeasible, show `Infeasible without reallocation` plus the reason per service, **not** a numeric savings value.
- If A itself is infeasible, B1 is undefined; say so.
- Identity: (A → B1) − (B1 → B2) = (A → B2). Distinguish **route change** from **optimizer value**.
- **Target allocation change** B1 → B2 per service (= `fleet_moves`, since B1 uses A's counts): a steady-state difference, not a repositioning schedule.
- Display changes per service in vessel count, speed, cycle days, slack, fuel tonnes/week, fuel cost, incremental vessel operating cost, idle fleet.

Do not assert that allocations must differ between scenarios. If they do not, report unchanged allocation and changes in speed/cost.

## 9. Map and simulated vessel movement: correct conceptual model

Map is **illustrative animation of the solution**, not a dynamic simulation engine, live AIS feed, forecast of real ship positions, or input into optimization.

- Each default service has authored, **separate westbound and eastbound waypoint sequences** per route variant (westbound Cape; eastbound Suez and eastbound Cape) in `app/data.py`, passing through the named port calls of its rotation; eastbound is not a reversal of westbound. Never draw straight lines between ports that cross land. Services without authored waypoints are shown in tables/charts but not on the map.
- A ship's loop is the westbound path of the scenario's variant followed by the eastbound path. Sailing time `D_s/(24*v)` is spread over segments in proportion to their length (so it also follows edited distances), port time `P_s` is split equally over the named port calls, and the residual slack is held at the origin port.
- Three synchronized maps (A, B1, B2) share one synthetic clock and viewport; each uses its own plan's routing, vessel count and speed from the same optimization run. B1 uses A's vessel counts with B1's recomputed speeds. A service filter only changes the display. If a plan is infeasible, routes are drawn but no ships are animated and the reason is shown.
- Animation time is a **synthetic model day**; ships on one service depart 7 simulated days apart. For `n` ships, `phase_i = (clock_days − 7*i) mod (7*n)`.
- Scenario switch redraws routes and recomputes the animation from that scenario's own optimized allocation; these are *separate steady states*, not a real-time rerouting transition.

## 10. Boundaries, assumptions, non-goals

- Homogeneous, company-owned vessels (one fuel curve, one incremental operating cost); one average sailing speed per service for both directions; fixed weekly departure frequency; route sequence fixed inside each scenario.
- Fuel at sea per nautical mile proportional to `v²` (fuel per day proportional to `v³`).
- No cargo demand, vessel capacity, transshipment, OD guarantees, network flow, vessel identities, port congestion randomness, carbon policy, canal tolls, repositioning costs/times, weather, or emissions accounting in MVP.
- `P_s` excludes the buffer; no double counting.
- Available fleet `F` is a parameter, **not necessarily all vessels deployed**.
- Source inspiration: D. Ronen, *The effect of oil price on containership speed and fleet size*, JORS 2011; Q. Meng and S. Wang, *Optimal operating strategy for a long-haul liner service route*, EJOR 2011. This demo is an **original simplification/multi-service extension**, not an implementation of their complete models.

## 11. Acceptance criteria

1. Both scenarios optimize using OR-Tools (SCIP) and return per-service selected `n`, speed, breakdowns, and solver status.
2. For any OPTIMAL/FEASIBLE solution, an independent verifier checks: one option per service, allocated `≤ F`, speed bounds, weekly frequency with effective buffer, C6/C8 when enabled, cost consistency.
3. At least one user-selectable limit demonstrably changes the optimal solution **or** correctly yields infeasibility.
4. Compare A, B1 and B2 accurately. No savings figure for infeasible B1.
5. Show disclaimers for estimated inputs and the stylized map animation.
6. Recompute all results after any input/constraint change; never reuse stale results.
7. Total distance per scenario equals the sum of its directional legs; directional routing is verified in tests.
