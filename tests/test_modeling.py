import math

import pytest

from app.modeling import (
    ScenarioProblem, ServiceRoute, build_option, build_options, cycle_speed,
    frequency_speed, fuel_coefficient, infeasibility_diagnostics, time_rule_violations,
)

ROUTE = ServiceRoute("S1", round_trip_nm=22000, port_days=20)


def make_problem(routes=(ROUTE,), fleet=30, v_min=12.0, v_max=22.0, buffer=None, tmax=None, caps=None,
                 fuel_price=600.0, deploy=100000.0):
    return ScenarioProblem(
        scenario="suez_available", services=list(routes), available_vessels=fleet,
        min_speed_knots=v_min, max_speed_knots=v_max, fuel_coeff=fuel_coefficient(18, 100),
        fuel_price=fuel_price, deployment_cost=deploy,
        buffer_days=buffer or {}, max_cycle_days=tmax or {}, max_fleet=caps or {},
    )


def test_fuel_coefficient_reproduces_reference_daily_fuel():
    c = fuel_coefficient(18, 100)
    # daily fuel at v = c * v^2 * (24 v) nm/day
    assert c * 18 ** 2 * 24 * 18 == pytest.approx(100)


def test_frequency_speed_formula_and_impossible_window():
    assert frequency_speed(22000, 20, 2, 10) == pytest.approx(22000 / (24 * 48))
    assert math.isinf(frequency_speed(22000, 20, 1, 3))  # 21 - 20 - 1 = 0
    assert math.isinf(frequency_speed(22000, 20, 0, 2))  # negative window


def test_cycle_speed_off_impossible_and_formula():
    assert cycle_speed(22000, 20, None) == 0.0
    assert math.isinf(cycle_speed(22000, 20, 20))
    assert cycle_speed(22000, 20, 80) == pytest.approx(22000 / (24 * 60))


def test_option_frequency_binding_with_buffer():
    p = make_problem(buffer={"S1": 2})
    o = build_option(p, ROUTE, 10)
    assert o.speed_binding == "frequency"
    assert o.speed == pytest.approx(22000 / (24 * 48))
    assert o.slack_days == pytest.approx(2)  # exactly the buffer
    assert not time_rule_violations(p, ROUTE, o)


def test_effective_buffer_is_zero_when_c7_off():
    o = build_option(make_problem(), ROUTE, 10)
    assert o.speed == pytest.approx(22000 / (24 * 50))
    assert o.slack_days == pytest.approx(0)


def test_min_speed_plateau_adds_slack():
    p = make_problem()
    o = build_option(p, ROUTE, 20)  # frequency would need only 22000/(24*120) kn
    assert o.speed_binding == "min_speed"
    assert o.speed == 12
    assert o.slack_days == pytest.approx(140 - (22000 / (24 * 12) + 20))


def test_max_cycle_binding():
    p = make_problem(tmax={"S1": 70})
    o = build_option(p, ROUTE, 20)
    assert o.speed_binding == "max_cycle"
    assert o.speed == pytest.approx(22000 / (24 * 50))
    assert o.active_cycle_days == pytest.approx(70)
    assert not time_rule_violations(p, ROUTE, o)


def test_required_speed_above_max_is_capped_and_violates_c4():
    p = make_problem(buffer={"S1": 2})
    o = build_option(p, ROUTE, 9)  # needs 22000/(24*41) = 22.36 kn
    assert o.speed_binding == "max_speed_cap"
    assert o.required_speed == pytest.approx(22000 / (24 * 41))
    assert o.speed == 22
    assert o.sailing_days + 20 + 2 > 63
    assert time_rule_violations(p, ROUTE, o)


def test_no_valid_speed_does_not_divide_by_zero():
    p = make_problem(buffer={"S1": 1})
    o = build_option(p, ROUTE, 3)
    assert math.isinf(o.required_speed) and o.speed == 22
    assert "no speed works" in time_rule_violations(p, ROUTE, o)[0]


def test_exactly_max_speed_is_accepted_within_tolerance():
    # choose D so that n=10 needs exactly 22 kn: D = 22 * 24 * (70 - 20)
    route = ServiceRoute("S1", 22 * 24 * 50, 20)
    p = make_problem(routes=(route,))
    o = build_option(p, route, 10)
    assert o.speed == pytest.approx(22)
    assert o.speed_binding != "max_speed_cap"
    assert not time_rule_violations(p, route, o)


def test_tmax_not_above_port_time_is_reported():
    p = make_problem(tmax={"S1": 20})
    o = build_option(p, ROUTE, 20)
    assert any("not above port time" in v for v in time_rule_violations(p, ROUTE, o))


def test_cost_formula():
    p = make_problem(fuel_price=500, deploy=50000)
    o = build_option(p, ROUTE, 12)
    expected_fuel_t = fuel_coefficient(18, 100) * 22000 * o.speed ** 2
    assert o.fuel_tonnes_week == pytest.approx(expected_fuel_t)
    assert o.fuel_cost_week == pytest.approx(500 * expected_fuel_t)
    assert o.deployment_cost_week == pytest.approx(12 * 50000)
    assert o.total_cost_week == pytest.approx(o.fuel_cost_week + o.deployment_cost_week)


def test_fuel_price_does_not_change_speed_only_cost():
    lo = build_option(make_problem(fuel_price=200), ROUTE, 12)
    hi = build_option(make_problem(fuel_price=900), ROUTE, 12)
    assert lo.speed == hi.speed
    assert hi.fuel_cost_week == pytest.approx(4.5 * lo.fuel_cost_week)


def test_build_options_covers_every_fleet_size():
    r2 = ServiceRoute("S2", 15000, 10)
    opts = build_options(make_problem(routes=(ROUTE, r2), fleet=25))
    assert set(opts) == {"S1", "S2"}
    assert list(opts["S1"]) == list(range(1, 26))


def test_diagnostics_minimum_fleet_and_shortfall():
    r2 = ServiceRoute("S2", 15000, 10)
    p = make_problem(routes=(ROUTE, r2), fleet=12, buffer={"S1": 2, "S2": 2})
    d = infeasibility_diagnostics(p, build_options(p))
    assert d["min_vessels_by_service"]["S1"] == 10
    s2_min = d["min_vessels_by_service"]["S2"]
    assert s2_min == math.ceil((15000 / (24 * 22) + 12) / 7)
    assert d["total_min_vessels"] == 10 + s2_min
    assert any("only 12 available" in r for r in d["reasons"])


def test_diagnostics_service_with_no_fleet_size_and_low_cap():
    r2 = ServiceRoute("S2", 15000, 10)
    p = make_problem(routes=(ROUTE, r2), tmax={"S1": 50}, caps={"S2": 2})
    d = infeasibility_diagnostics(p, build_options(p))
    assert d["min_vessels_by_service"]["S1"] is None
    assert d["total_min_vessels"] is None
    assert any(r.startswith("S1: no fleet size") for r in d["reasons"])
    assert any("S2: fleet cap 2" in r for r in d["reasons"])


def test_polyline_nm_one_degree_of_latitude_is_60nm():
    from app.modeling import polyline_nm
    assert polyline_nm([[0, 0], [1, 0]]) == pytest.approx(60.04, abs=0.05)
    assert polyline_nm([[0, 0], [1, 0], [2, 0, "Port"]]) == pytest.approx(2 * 60.04, abs=0.1)
    assert polyline_nm([[10, 10]]) == 0


def test_scenario_round_trip_is_sum_of_directional_legs():
    from app.modeling import scenario_round_trip_nm
    legs = {"westbound": {"cape": 15000}, "eastbound": {"suez": 11000, "cape": 15500}}
    assert scenario_round_trip_nm(legs, {"westbound": "cape", "eastbound": "suez"}) == 26000
    assert scenario_round_trip_nm(legs, {"westbound": "cape", "eastbound": "cape"}) == 30500
