"""FastAPI routes, response serialization and static frontend mount."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import data
from app.comparison import Comparison, FixedEvaluation, compare
from app.modeling import Option, ScenarioProblem
from app.schemas import CompareRequest, OptimizeRequest
from app.solver import SOLVER_NAME, SolveResult, VerificationError, solve

VERSION = "0.1.0"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("fleet")

app = FastAPI(title="Liner Fleet & Speed Optimizer", version=VERSION)


@app.middleware("http")
async def _revalidate_frontend(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"  # static files: always revalidate (ETag), never serve stale
    return response


@app.exception_handler(VerificationError)
async def _verification_failed(_: Request, exc: VerificationError):
    log.error("verification failed: %s", exc)
    return JSONResponse(status_code=500, content={
        "error": "verification_failed",
        "detail": "The solver returned a plan that failed independent verification; it was not displayed.",
        "violations": str(exc)})


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception):
    log.exception("unexpected server error")
    return JSONResponse(status_code=500, content={"error": "server_error",
                                                  "detail": "Unexpected server error; see server log."})


def _service_json(o: Option) -> dict:
    return {
        "service_id": o.service_id,
        "selected_vessels": o.n,
        "speed_knots": o.speed,
        "speed_binding": o.speed_binding,
        "sailing_days": o.sailing_days,
        "active_cycle_days": o.active_cycle_days,
        "scheduled_rotation_days": o.rotation_days,
        "slack_days": o.slack_days,
        "fuel_tonnes_week": o.fuel_tonnes_week,
        "fuel_cost_usd_week": o.fuel_cost_week,
        "deployment_cost_usd_week": o.deployment_cost_week,
        "total_cost_usd_week": o.total_cost_week,
    }


def _metrics(plan: dict[str, Option], problem: ScenarioProblem) -> dict:
    allocated = sum(o.n for o in plan.values())
    return {
        "total_cost_usd_week": sum(o.total_cost_week for o in plan.values()),
        "fuel_cost_usd_week": sum(o.fuel_cost_week for o in plan.values()),
        "deployment_cost_usd_week": sum(o.deployment_cost_week for o in plan.values()),
        "allocated_vessels": allocated,
        "available_vessels": problem.available_vessels,
        "idle_vessels": problem.available_vessels - allocated,
    }


def _result_json(r: SolveResult, problem: ScenarioProblem) -> dict:
    out = {
        "scenario": r.scenario,
        "status": r.status,
        "solver": SOLVER_NAME,
        "solve_time_ms": r.solve_time_ms,
        "model_size": {"binary_variables": r.num_variables, "constraints": r.num_constraints},
        "metadata": {"estimated_inputs": True},
    }
    if r.has_solution:
        out["objective_usd_week"] = r.objective
        out["metrics"] = _metrics(r.plan, problem)
        out["services"] = [_service_json(r.plan[s.service_id]) for s in problem.services]
        out["verification"] = {"passed": True, "violations": []}
    elif r.status == "INFEASIBLE":
        out["reason"] = "No feasible allocation under the selected inputs and constraints."
        out["diagnostics"] = r.diagnostics
    else:
        out["reason"] = f"Solver ended with status {r.status}; no solution available."
    return out


def _fixed_json(f: FixedEvaluation | None, problem: ScenarioProblem) -> dict | None:
    if f is None:
        return None
    out = {"feasible": f.feasible, "reasons": f.reasons,
           "allocation": {s: o.n for s, o in f.plan.items()}}
    if f.feasible:
        out["metrics"] = _metrics(f.plan, problem)
        out["services"] = [_service_json(f.plan[s.service_id]) for s in problem.services]
    else:
        out["speeds_required_knots"] = {s: (None if o.required_speed == float("inf") else o.required_speed)
                                        for s, o in f.plan.items()}
    return out


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION, "solver": SOLVER_NAME}


@app.get("/api/config")
def config():
    return {
        "defaults": data.DEFAULT_INPUT,
        "scenarios": data.SCENARIOS,
        "bounds": data.INPUT_BOUNDS,
        "routes": data.ROUTES,
        "disclaimers": data.DISCLAIMERS,
        "sources": data.SOURCES,
        "service_meta": data.SERVICE_META,
        "port_days_per_call": data.PORT_DAYS_PER_CALL,
        "solver": SOLVER_NAME,
    }


@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    problem = req.to_problem(req.scenario)
    return _result_json(solve(problem), problem)


@app.post("/api/compare")
def compare_scenarios(req: CompareRequest):
    pa, pb = req.to_problem("mixed_routing"), req.to_problem("full_cape")
    c: Comparison = compare(pa, pb)
    return {
        "a": _result_json(c.a, pa),
        "b": _result_json(c.b, pb),
        "b_fixed": _fixed_json(c.b_fixed, pb),
        "disruption_impact_usd_week": c.disruption_impact,
        "disruption_impact_pct": c.disruption_impact_pct,
        "fixed_fleet_impact_usd_week": c.fixed_fleet_impact,
        "reoptimization_savings_usd_week": c.reoptimization_savings,
        "fleet_moves": c.fleet_moves,
    }


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
