"""A (Suez optimal) vs B (Cape optimal) vs B_fixed (Cape with A's counts), 01 §8."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.modeling import Option, ScenarioProblem, build_option, time_rule_violations
from app.solver import SolveResult, solve


@dataclass
class FixedEvaluation:
    """B evaluated with A's fleet counts; speeds recomputed under B."""
    feasible: bool
    plan: dict[str, Option] = field(default_factory=dict)
    total_cost: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class Comparison:
    a: SolveResult
    b: SolveResult
    b_fixed: FixedEvaluation | None   # None when A has no solution
    disruption_impact: float | None   # Cost_B* - Cost_A*
    fixed_fleet_impact: float | None  # Cost_B_fixed - Cost_A*, only if B_fixed feasible
    disruption_impact_pct: float | None
    reoptimization_savings: float | None  # Cost_B_fixed - Cost_B*, only if B_fixed feasible
    fleet_moves: dict[str, int] | None   # n_B - n_A per service


def evaluate_fixed(problem_b: ScenarioProblem, counts: dict[str, int]) -> FixedEvaluation:
    plan, reasons = {}, []
    for route in problem_b.services:
        opt = build_option(problem_b, route, counts[route.service_id])
        plan[route.service_id] = opt
        reasons.extend(time_rule_violations(problem_b, route, opt))
    if reasons:
        return FixedEvaluation(feasible=False, plan=plan, reasons=reasons)
    return FixedEvaluation(feasible=True, plan=plan,
                           total_cost=sum(o.total_cost_week for o in plan.values()))


def compare(problem_a: ScenarioProblem, problem_b: ScenarioProblem) -> Comparison:
    a, b = solve(problem_a), solve(problem_b)

    b_fixed = None
    if a.has_solution:
        b_fixed = evaluate_fixed(problem_b, {s: o.n for s, o in a.plan.items()})

    impact = impact_pct = moves = savings = fixed_impact = None
    if b_fixed is not None and b_fixed.feasible:
        fixed_impact = b_fixed.total_cost - a.objective
    if a.has_solution and b.has_solution:
        impact = b.objective - a.objective
        impact_pct = 100.0 * impact / a.objective if a.objective > 0 else None
        moves = {s: b.plan[s].n - a.plan[s].n for s in a.plan}
        if b_fixed is not None and b_fixed.feasible:
            savings = b_fixed.total_cost - b.objective
    return Comparison(a=a, b=b, b_fixed=b_fixed, disruption_impact=impact, fixed_fleet_impact=fixed_impact,
                      disruption_impact_pct=impact_pct, reoptimization_savings=savings, fleet_moves=moves)
