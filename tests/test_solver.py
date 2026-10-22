import itertools

import pytest

from app.modeling import ScenarioProblem, ServiceRoute, build_options, fuel_coefficient, time_rule_violations
from app.solver import solve

ROUTES = [ServiceRoute("S1", 29500, 21), ServiceRoute("S2", 26000, 16), ServiceRoute("S3", 12500, 12)]


def make_problem(routes=ROUTES, fleet=38, **kw):
    base = dict(scenario="cape_diversion", services=list(routes), available_vessels=fleet,
                min_speed_knots=12.0, max_speed_knots=22.0, fuel_coeff=fuel_coefficient(18, 100),
                fuel_price=600.0, deployment_cost=150000.0, buffer_days={r.service_id: 2 for r in routes})
    base.update(kw)
    return ScenarioProblem(**base)


def brute_force(problem):
    """Exhaustive enumeration of every combination of fleet sizes."""
    options = build_options(problem)
    routes = {r.service_id: r for r in problem.services}
    ids = list(options)
    best = None
    for combo in itertools.product(*(options[s].values() for s in ids)):
        if sum(o.n for o in combo) > problem.available_vessels:
            continue
        if any(time_rule_violations(problem, routes[o.service_id], o) for o in combo):
            continue
        if any(o.n > problem.max_fleet.get(o.service_id, 10 ** 9) for o in combo):
            continue
        cost = sum(o.total_cost_week for o in combo)
        if best is None or cost < best[0]:
            best = (cost, {o.service_id: o.n for o in combo})
    return best


def test_optimal_and_one_option_per_service_within_fleet():
    r = solve(make_problem())
    assert r.status == "OPTIMAL"
    assert set(r.plan) == {"S1", "S2", "S3"}
    assert sum(o.n for o in r.plan.values()) <= 38
    assert r.verification == []
    assert r.num_variables == 3 * 38


@pytest.mark.parametrize("kw", [
    {},
    {"available_vessels": 44},
    {"available_vessels": 30},
    {"fuel_price": 250.0},
    {"deployment_cost": 40000.0},
    {"max_fleet": {"S1": 14}},
    {"max_cycle_days": {"S2": 100}},
])
def test_matches_brute_force(kw):
    p = make_problem(**kw)
    r = solve(p)
    cost, alloc = brute_force(p)
    assert r.status == "OPTIMAL"
    assert r.objective == pytest.approx(cost, rel=1e-9)
    assert {s: o.n for s, o in r.plan.items()} == alloc


def test_options_needing_speed_above_max_are_never_selected():
    r = solve(make_problem(fleet=28))  # exactly the minimum fleet
    assert r.status == "OPTIMAL"
    for o in r.plan.values():
        assert o.speed_binding != "max_speed_cap"
        assert o.speed <= 22


def test_cap_changes_solution():
    free = solve(make_problem())
    capped = solve(make_problem(max_fleet={"S1": 14}))
    assert free.plan["S1"].n > 14
    assert capped.plan["S1"].n <= 14
    assert capped.objective > free.objective


def test_tmax_changes_solution():
    free = solve(make_problem())
    tight = solve(make_problem(max_cycle_days={"S2": 90}))
    assert tight.plan["S2"].active_cycle_days <= 90 + 1e-9
    assert tight.plan["S2"].speed > free.plan["S2"].speed


def test_infeasible_fleet_too_small_with_diagnostics():
    r = solve(make_problem(fleet=25))
    assert r.status == "INFEASIBLE"
    assert r.plan is None and r.objective is None
    assert r.diagnostics["total_min_vessels"] == 28
    assert any("only 25 available" in x for x in r.diagnostics["reasons"])


def test_infeasible_impossible_tmax():
    r = solve(make_problem(max_cycle_days={"S1": 21}))
    assert r.status == "INFEASIBLE"
    assert r.diagnostics["min_vessels_by_service"]["S1"] is None


def test_exactly_max_speed_option_is_feasible():
    route = ServiceRoute("S1", 22 * 24 * 50, 20)  # n=10 needs exactly 22 kn
    r = solve(make_problem(routes=[route], fleet=10, buffer_days={}))
    assert r.status == "OPTIMAL"
    assert r.plan["S1"].n == 10
    assert r.plan["S1"].speed == pytest.approx(22)
