import pytest

from app.comparison import compare, evaluate_fixed
from app.modeling import ScenarioProblem, ServiceRoute, fuel_coefficient

SUEZ = [ServiceRoute("S1", 23000, 21), ServiceRoute("S2", 17500, 16), ServiceRoute("S3", 12500, 12)]
CAPE = [ServiceRoute("S1", 29500, 21), ServiceRoute("S2", 26000, 16), ServiceRoute("S3", 12500, 12)]


def make(scenario, routes, fleet=38, v_max=22.0, **kw):
    base = dict(scenario=scenario, services=list(routes), available_vessels=fleet, min_speed_knots=12.0,
                max_speed_knots=v_max, fuel_coeff=fuel_coefficient(18, 100), fuel_price=600.0,
                deployment_cost=150000.0, buffer_days={"S1": 2, "S2": 2, "S3": 2})
    base.update(kw)
    return ScenarioProblem(**base)


def test_scenario_inputs_differ_for_affected_services_only():
    assert SUEZ[0] != CAPE[0] and SUEZ[1] != CAPE[1]
    assert SUEZ[2] == CAPE[2]


def test_feasible_b_fixed_gives_savings_and_metrics():
    r = compare(make("suez_available", SUEZ), make("cape_diversion", CAPE))
    assert r.a.status == r.b.status == "OPTIMAL"
    assert r.disruption_impact == pytest.approx(r.b.objective - r.a.objective)
    assert r.disruption_impact_pct == pytest.approx(100 * r.disruption_impact / r.a.objective)
    assert r.fleet_moves == {s: r.b.plan[s].n - r.a.plan[s].n for s in r.a.plan}
    assert r.b_fixed.feasible
    assert {s: o.n for s, o in r.b_fixed.plan.items()} == {s: o.n for s, o in r.a.plan.items()}
    assert r.reoptimization_savings == pytest.approx(r.b_fixed.total_cost - r.b.objective)
    assert r.reoptimization_savings >= -1e-6  # B* is optimal over a superset incl. A's counts


def test_b_fixed_recomputes_speed_under_cape():
    r = compare(make("suez_available", SUEZ), make("cape_diversion", CAPE))
    s2_a, s2_fixed = r.a.plan["S2"], r.b_fixed.plan["S2"]
    assert s2_fixed.n == s2_a.n
    assert s2_fixed.speed > s2_a.speed  # longer route, same ships -> faster
    assert s2_fixed.speed == pytest.approx(26000 / (24 * (7 * s2_a.n - 16 - 2)))


def test_infeasible_b_fixed_has_no_savings():
    r = compare(make("suez_available", SUEZ, v_max=17), make("cape_diversion", CAPE, v_max=17))
    assert r.b.status == "OPTIMAL"
    assert not r.b_fixed.feasible
    assert r.b_fixed.total_cost is None
    assert r.reoptimization_savings is None
    assert any(x.startswith("S2:") for x in r.b_fixed.reasons)
    assert r.disruption_impact is not None


def test_a_infeasible_means_no_b_fixed():
    r = compare(make("suez_available", SUEZ, fleet=20), make("cape_diversion", CAPE, fleet=20))
    assert r.a.status == "INFEASIBLE"
    assert r.b_fixed is None
    assert r.disruption_impact is None and r.reoptimization_savings is None and r.fleet_moves is None


def test_evaluate_fixed_directly():
    ev = evaluate_fixed(make("cape_diversion", CAPE), {"S1": 15, "S2": 11, "S3": 8})
    assert ev.feasible
    assert ev.total_cost == pytest.approx(sum(o.total_cost_week for o in ev.plan.values()))


def test_fixed_fleet_impact_and_identity_of_three_comparisons():
    r = compare(make("suez_available", SUEZ), make("cape_diversion", CAPE))
    assert r.fixed_fleet_impact == pytest.approx(r.b_fixed.total_cost - r.a.objective)
    # (B1 - A) - (B1 - B2) == B2 - A
    assert r.fixed_fleet_impact - r.reoptimization_savings == pytest.approx(r.disruption_impact)


def test_fixed_fleet_impact_none_when_b_fixed_infeasible():
    r = compare(make("suez_available", SUEZ, v_max=17), make("cape_diversion", CAPE, v_max=17))
    assert r.fixed_fleet_impact is None
