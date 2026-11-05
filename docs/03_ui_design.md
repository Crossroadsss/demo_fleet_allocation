# 03 — UI / UX Specification: Liner Fleet Optimizer

**Product type:** B2B maritime fleet-planning decision tool (single HTML app, vanilla JS) — product-quality experience, limited demo scope, real optimization logic.  
**Audience:** Fleet planners and operations managers (decisions first); OR engineers (methodology second).  
**Goal:** Show what changes under a Red Sea disruption, what the optimization recommends, the modeled cost impact, and how allocation and sailing speed differ — all from a real OR-Tools (SCIP) solve.

Read `01_optimization_model.md` for model meanings and `02_fullstack_architecture.md` for mechanics.

## 1. Structure

A persistent left sidebar (sticky on desktop; compact top navigation on phones) with three pages in this order:

1. **Decision Dashboard** — default landing page. On load it runs `/api/compare` on the default scenario, so it opens on real results.
2. **Scenario Configuration** — all editable inputs; primary action **Run optimization**.
3. **Model & Methodology** — complete formulation for technical discussion.

One HTML document; JavaScript switches pages and keeps shared state (inputs, the inputs snapshot of the last run, the last comparison). The sidebar shows a `stale` badge when results no longer match the inputs. No page-wide disclaimer banner: one short line at the bottom of the sidebar ("Illustrative planning data"), a short note at the maps (illustrative movements, not live tracking), and the full assumptions, sources and limitations on Model & Methodology. Solver technology is named only on Model & Methodology and in the verification details, not in the sidebar.

## 2. Decision Dashboard

Story: original plan → what changed under routing disruption → what fleet reoptimization recommends → resulting cost. Wide layout (up to 1680 px). Operator-facing plan names only — **Baseline** (mixed routing, fleet and speeds optimized), **Unchanged Fleet** (full Cape, Baseline vessel counts, speeds recomputed), **Optimized Fleet** (full Cape, fleet and speeds re-optimized); A/B1/B2 stay internal (API keys `a`, `b_fixed`, `b`; Model & Methodology maps the names). Colors: Baseline teal, Unchanged Fleet gray, Optimized Fleet orange; services FAL2 blue, FAL3 purple, FAL5 magenta. The status line is hidden when all plans are proven optimal and shown for loading, feasible-not-proven, out-of-date and error states.

1. **Operating Plan Comparison** — three plan cards (name, routing, total weekly cost, "proven optimal" / "feasible · optimality not proven" / "evaluated", vessels deployed) joined by two arrows that carry the cost changes:
   - **Routing disruption** (Baseline → Unchanged Fleet): Cost(Unchanged Fleet) − Cost(Baseline), e.g. "+$2.96M / week" with the defaults.
   - **Fleet reoptimization** (Unchanged Fleet → Optimized Fleet): Cost(Unchanged Fleet) − Cost(Optimized Fleet), shown as "$X / week saved" — "$0 / week saved" when the solver finds no reduction (not treated as a failure); **N/A** with explanation when the Unchanged Fleet is infeasible; qualified when optimality is not proven.
   - A **Recommended action** banner generated from the results (maintain allocation and speed up / reallocate with the actual changes / reallocation required), with **Net impact vs Baseline (optimized)** = Cost(Optimized Fleet) − Cost(Baseline) as the secondary figure. Stacks vertically with downward arrows on narrow screens.
2. **Fleet Movement Comparison** — three synchronized maps (§3).
3. **Fleet Allocation and Sailing Speed** — three compact panels: fleet allocation table (Baseline, Unchanged Fleet, Optimized Fleet, change Optimized − Unchanged; changes highlighted; totals), two vertical bar charts with one shared layout (same height, margins, fonts, gridlines, axis lines and label format): **Sailing speed by service** — grouped bars per service, one labeled bar per plan (identical speeds show as two equal bars), y-axis "Sailing speed (kn) · axis starts at N kn" (non-zero start stated); **Weekly operating cost** — one bar per plan starting at zero, y-axis "Weekly operating cost (USD million/week)". Both have the same HTML legend line above the chart (Baseline teal, Unchanged Fleet gray, Optimized Fleet orange), fitting one line from 1280 px; plot areas align (bottom-anchored in equal-height panels).
4. **Detailed Analysis** (collapsed) — cost breakdown fuel vs incremental vessel operating cost (rendered on open), service-level metrics with definitions (**Active cycle** = sailing + port time; **Scheduled rotation** = 7 × vessels; **Schedule slack** = rotation − active cycle, with the C7 buffer as its required minimum), route distances, cost calculation details with reconciliation, solver status and verification.

## 3. Fleet Movement Comparison (three synchronized maps)

- Three Leaflet maps in one row on desktop (stacked on narrow screens) with compact headers: **Baseline** (mixed routing · EB via Suez), **Unchanged Fleet** (full Cape), **Optimized Fleet** (full Cape). The two full-Cape maps use identical geometry; differences come from vessel counts and speeds.
- **Service checkboxes** FAL2 / FAL3 / FAL5 (all checked by default) with **All** and **Clear**; any combination, applied to all three maps at once. Each checkbox carries the route-color bar, so it is the legend — no separate map legend. Filtering never reruns the optimization or resets the clock.
- **Route click** highlights that service on all three maps (thicker line, others dimmed but visible, matching checkbox outlined); clicking the route again or empty map clears it.
- **Shared playback bar** under the maps: play/pause, timeline scrubber, synthetic day, playback rate, Reset, Fit-all-routes. Pan/zoom linked across maps.
- **Map info overlay** (top-right of each map): service, vessels, speed (kn) for the selected services, plus fleet deployed / idle when all are shown; "No services selected" when the filter is empty. Active cycle, rotation and slack live in Detailed Analysis.
- Infeasible plan: routes drawn, no ships, explanatory overlay. Suez Canal and Cape of Good Hope labeled; port names on hover (all from zoom 5). Illustrative steady state — not AIS or a repositioning plan.

## 4. Scenario Configuration

- **Configuration summary** chips (fleet, speed range, bunker, vessel operating cost, services, C6/C7/C8 on/off with values).
- **Fleet & vessel characteristics:** available vessels, reference speed, fuel at reference speed, min / max speed, derived fuel coefficient (read-only).
- **Economics:** bunker price; **Incremental vessel operating cost (USD/vessel/week)** with tooltip (excl. fuel, versus idle; not acquisition/depreciation/charter); illustrative-defaults note.
- **Service and routing data:** direction legend (Westbound = Asia → Europe, Eastbound = Europe → Asia, round trip = sum of legs), live routing diagram (stacked leg bars and totals per service and scenario), and the table with column groups *Westbound · via Cape*, *Eastbound · via Suez / via Cape*, *Calculated round trip* (read-only), plus port days per loop. Service-name tooltip shows the port rotation.
- **Business constraints** in plain language, without constraint numbers or formulas (those stay on Model & Methodology). *Optional settings* (checkbox + per-service values): **Maximum Vessels per Service**, **Minimum Schedule Buffer** (days per round trip: spare days built into every round trip to absorb delays while keeping weekly departures; more buffer → faster sailing or more vessels), **Maximum Round-Trip Duration** (days per round trip: limits the active time of one round trip — sailing plus port time, not counting spare buffer days; a tighter limit forces faster sailing). *Always applied*: **One Fleet Allocation per Service**, **Fleet Availability**, **Weekly Departures**, **Sailing Speed Limits**. Each setting controls the same backend rule field as before (`max_fleet_per_service`, `minimum_schedule_buffer`, `maximum_round_trip_time`).
- Actions: **Reset to defaults**, **Run optimization** (top and bottom; shows "Running optimization…" while busy). On success the app navigates to the dashboard. Validation errors (422) appear at the top of this page and the dashboard results are cleared.

## 5. Model & Methodology

- **Business problem** with the statement: "FAL2, FAL3, and FAL5 were selected as representative CMA CGM Asia–North Europe liner services to demonstrate how Red Sea routing disruptions affect fleet allocation, sailing speeds, and operating costs." Four tiles: **primary decision** (vessels per service), **derived** sailing speed, **objective**, **essential rules**; the two scenario cards with directional routing.
- **Key assumptions** and the **owned-fleet note** (`h = h_active − h_idle`).
- **Constraints** C1–C8 as a compact list (name, meaning, formula, mandatory/optional).
- Expandable: full mathematical formulation (incl. why an exact 0–1 MILP), constraint implementation, optimization workflow, limitations and data sources (incl. port rotations).

## 6. States

Loading (spinner, disabled buttons) · optimal · feasible-not-proven-optimal (amber) · infeasible plan (per card, map overlay) · out of date (inputs changed: sidebar badge, faded results, banner with Rerun) · validation error · server error. No NaN, `undefined` or stale values are displayed as valid results.

## 7. Demo walkthrough

1. Dashboard opens on the default run: Baseline → routing disruption → Unchanged Fleet → fleet reoptimization → Optimized Fleet, and the recommended action.
2. With the default pool of 50 vessels the Baseline leaves vessels idle; under full Cape the Optimized Fleet deploys them, so reoptimization saves money versus the Unchanged Fleet. Use the maps to compare vessel counts and speeds.
3. Scenario Configuration: set the fleet to the published 44 → every vessel is already deployed in the Baseline, the solver keeps the allocation and speeds up ($0/week saved); at 50 vessels with max speed 14 kn → Unchanged Fleet infeasible, Optimized Fleet reallocates. Filter the maps to one or two services and click a route to highlight it.
4. Model & Methodology: decision vs derived speed, 0–1 MILP, why it is exact.
