"""OR-Tools pywraplp / SCIP 0-1 MILP for fleet allocation (01 §6).

All options n = 1..F enter the model; every rule (C1-C8) is a linear row
over the binaries y[s,n], using the per-option coefficients from
modeling.py. The solver alone decides feasibility.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.linear_solver import pywraplp

from app.modeling import TIME_TOL_DAYS, Option, ScenarioProblem, build_options, infeasibility_diagnostics
from app.verifier import verify

SOLVER_NAME = "ORTOOLS_SCIP"
TIME_LIMIT_MS = 10_000

_STATUS = {
    pywraplp.Solver.OPTIMAL: "OPTIMAL",
    pywraplp.Solver.FEASIBLE: "FEASIBLE",
    pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
    pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
    pywraplp.Solver.ABNORMAL: "ABNORMAL",
    pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    pywraplp.Solver.MODEL_INVALID: "MODEL_INVALID",
}


class VerificationError(RuntimeError):
    """The solver returned a plan that fails the independent verifier."""


@dataclass
class SolveResult:
    scenario: str
    status: str
    solve_time_ms: float
    plan: dict[str, Option] | None = None
    objective: float | None = None
    diagnostics: dict | None = None
    num_variables: int = 0
    num_constraints: int = 0
    verification: list[str] = field(default_factory=list)

    @property
    def has_solution(self) -> bool:
        return self.plan is not None


def solve(problem: ScenarioProblem, time_limit_ms: int = TIME_LIMIT_MS) -> SolveResult:
    options = build_options(problem)
    routes = {r.service_id: r for r in problem.services}

    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("SCIP backend unavailable in this OR-Tools build")

    y = {(s, n): solver.BoolVar(f"y_{s}_{n}") for s, opts in options.items() for n in opts}

    for s, opts in options.items():
        P, buf = routes[s].port_days, problem.buffer(s)
        solver.Add(sum(y[s, n] for n in opts) == 1, f"C1_one_option_{s}")
        solver.Add(sum((o.sailing_days + P + buf - 7 * n) * y[s, n] for n, o in opts.items())
                   <= TIME_TOL_DAYS, f"C4_weekly_frequency_{s}")
        v_sel = sum(o.speed * y[s, n] for n, o in opts.items())
        solver.Add(v_sel >= problem.min_speed_knots, f"C5_min_speed_{s}")
        solver.Add(v_sel <= problem.max_speed_knots, f"C5_max_speed_{s}")
        if s in problem.max_fleet:
            solver.Add(sum(n * y[s, n] for n in opts) <= problem.max_fleet[s], f"C6_fleet_cap_{s}")
        tmax = problem.tmax(s)
        if tmax is not None:
            solver.Add(sum(o.sailing_days * y[s, n] for n, o in opts.items()) + P
                       <= tmax + TIME_TOL_DAYS, f"C8_max_round_trip_{s}")
    solver.Add(sum(n * y[s, n] for (s, n) in y) <= problem.available_vessels, "C2_fleet_pool")

    solver.Minimize(sum(options[s][n].total_cost_week * y[s, n] for (s, n) in y))
    solver.SetTimeLimit(time_limit_ms)

    t0 = time.perf_counter()
    code = solver.Solve()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    status = _STATUS.get(code, f"UNKNOWN_{code}")

    result = SolveResult(scenario=problem.scenario, status=status, solve_time_ms=elapsed_ms,
                         num_variables=solver.NumVariables(), num_constraints=solver.NumConstraints())

    if status in ("OPTIMAL", "FEASIBLE"):
        plan = {}
        for s, opts in options.items():
            chosen = [n for n in opts if y[s, n].solution_value() > 0.5]
            if len(chosen) != 1:
                raise VerificationError(f"{s}: solver selected {len(chosen)} options")
            plan[s] = opts[chosen[0]]
        objective = sum(o.total_cost_week for o in plan.values())
        violations = verify(problem, plan, objective)
        if violations:
            raise VerificationError("; ".join(violations))
        result.plan, result.objective = plan, objective
    elif status == "INFEASIBLE":
        result.diagnostics = infeasibility_diagnostics(problem, options)
    return result
