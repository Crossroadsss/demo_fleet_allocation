from dataclasses import replace

from app.modeling import ScenarioProblem, ServiceRoute, build_option, fuel_coefficient
from app.verifier import verify

R1 = ServiceRoute("S1", 22000, 20)
R2 = ServiceRoute("S2", 15000, 10)


def make_problem(**kw):
    base = dict(scenario="suez_available", services=[R1, R2], available_vessels=30,
                min_speed_knots=12.0, max_speed_knots=22.0, fuel_coeff=fuel_coefficient(18, 100),
                fuel_price=600.0, deployment_cost=100000.0)
    base.update(kw)
    return ScenarioProblem(**base)


def plan_for(problem, n1, n2):
    plan = {"S1": build_option(problem, R1, n1), "S2": build_option(problem, R2, n2)}
    return plan, sum(o.total_cost_week for o in plan.values())


def test_valid_plan_passes():
    p = make_problem(buffer_days={"S1": 2, "S2": 2})
    plan, total = plan_for(p, 12, 8)
    assert verify(p, plan, total) == []


def test_missing_service_flagged():
    p = make_problem()
    plan, total = plan_for(p, 12, 8)
    del plan["S2"]
    assert "plan services" in verify(p, plan, total)[0]


def test_fleet_over_available_flagged():
    p = make_problem(available_vessels=15)
    plan, total = plan_for(p, 12, 8)
    assert any("> available 15" in v for v in verify(p, plan, total))


def test_speed_out_of_bounds_flagged():
    p = make_problem()
    plan, total = plan_for(p, 12, 8)
    plan["S1"] = replace(plan["S1"], speed=25.0)
    assert any("outside" in v for v in verify(p, plan, total))


def test_frequency_and_buffer_violation_flagged():
    p = make_problem(buffer_days={"S1": 2})
    plan, total = plan_for(p, 9, 8)  # S1 with 9 ships needs 22.4 kn, capped at 22
    assert any("S1: sailing" in v for v in verify(p, plan, total))


def test_cap_violation_flagged():
    p = make_problem(max_fleet={"S2": 6})
    plan, total = plan_for(p, 12, 8)
    assert any("S2: 8 vessels > cap 6" in v for v in verify(p, plan, total))


def test_max_round_trip_violation_flagged():
    p = make_problem()
    plan, total = plan_for(p, 20, 8)  # S1 at v_min: ~96 d cycle
    p_tmax = make_problem(max_cycle_days={"S1": 80})
    assert any("max round trip 80" in v for v in verify(p_tmax, plan, total))


def test_cost_mismatch_flagged():
    p = make_problem()
    plan, total = plan_for(p, 12, 8)
    plan["S1"] = replace(plan["S1"], fuel_cost_week=plan["S1"].fuel_cost_week + 1000)
    assert any("fuel cost" in v for v in verify(p, plan, total))
    plan, total = plan_for(p, 12, 8)
    plan["S2"] = replace(plan["S2"], total_cost_week=plan["S2"].total_cost_week + 1000)
    assert any("S2: total cost" in v for v in verify(p, plan, total))


def test_objective_mismatch_flagged():
    p = make_problem()
    plan, total = plan_for(p, 12, 8)
    assert any("objective" in v for v in verify(p, plan, total + 5000))
