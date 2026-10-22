import copy
import warnings

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app import data
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def defaults(**top):
    body = copy.deepcopy(data.DEFAULT_INPUT)
    body.update(top)
    return body


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["solver"] == "ORTOOLS_SCIP"


def test_config_contains_defaults_routes_and_disclaimers():
    cfg = client.get("/api/config").json()
    assert cfg["defaults"] == data.DEFAULT_INPUT
    assert set(cfg["scenarios"]) == {"mixed_routing", "full_cape"}
    for s in data.DEFAULT_INPUT["services"]:
        route = cfg["routes"][s["service_id"]]
        assert len(route["westbound"]["cape"]) >= 2
        assert len(route["eastbound"]["suez"]) >= 2 and len(route["eastbound"]["cape"]) >= 2
    assert cfg["disclaimers"]


@pytest.mark.parametrize("scenario", ["mixed_routing", "full_cape"])
def test_defaults_solve_optimal_with_consistent_metrics(scenario):
    r = client.post("/api/optimize", json=defaults(scenario=scenario))
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "OPTIMAL" and j["solver"] == "ORTOOLS_SCIP"
    m = j["metrics"]
    assert abs(sum(s["total_cost_usd_week"] for s in j["services"]) - m["total_cost_usd_week"]) < 1e-6
    assert m["allocated_vessels"] == sum(s["selected_vessels"] for s in j["services"])
    assert m["allocated_vessels"] + m["idle_vessels"] == m["available_vessels"]
    assert j["verification"]["passed"]
    for s in j["services"]:
        assert s["slack_days"] >= 2 - 1e-9  # default C7 buffer is on


def test_compare_defaults():
    j = client.post("/api/compare", json=defaults()).json()
    assert j["a"]["status"] == j["b"]["status"] == "OPTIMAL"
    assert j["disruption_impact_usd_week"] == pytest.approx(
        j["b"]["metrics"]["total_cost_usd_week"] - j["a"]["metrics"]["total_cost_usd_week"])
    assert j["b_fixed"]["feasible"] is True
    assert j["reoptimization_savings_usd_week"] >= -1e-6
    assert j["fixed_fleet_impact_usd_week"] - j["reoptimization_savings_usd_week"] == pytest.approx(j["disruption_impact_usd_week"])
    assert j["b_fixed"]["allocation"] == {s["service_id"]: s["selected_vessels"] for s in j["a"]["services"]}


def test_compare_infeasible_b_fixed_has_null_savings():
    body = defaults()
    body["fleet"]["available_vessels"] = 50  # spare vessels: B2 adds ships, B1 keeps A's counts
    body["fleet"]["max_speed_knots"] = 14.0  # B1: A's counts would need more than 14 kn on full Cape
    j = client.post("/api/compare", json=body).json()
    assert j["b_fixed"]["feasible"] is False
    assert j["reoptimization_savings_usd_week"] is None
    assert j["b_fixed"]["reasons"]
    assert "metrics" not in j["b_fixed"]


def test_infeasible_response_has_no_solution_fields():
    body = defaults(scenario="full_cape")
    body["fleet"]["available_vessels"] = 25
    j = client.post("/api/optimize", json=body).json()
    assert j["status"] == "INFEASIBLE"
    assert "metrics" not in j and "services" not in j
    assert j["diagnostics"]["reasons"]


def test_rerun_after_toggle_changes_result():
    base = client.post("/api/optimize", json=defaults(scenario="full_cape")).json()
    body = defaults(scenario="full_cape")
    body["rules"]["max_fleet_per_service"]["enabled"] = True
    body["rules"]["max_fleet_per_service"]["limits"]["FAL2"] = 13
    capped = client.post("/api/optimize", json=body).json()
    assert capped["status"] == "OPTIMAL"
    assert capped["metrics"]["total_cost_usd_week"] > base["metrics"]["total_cost_usd_week"]


def _mutate(path, value):
    body = defaults(scenario="mixed_routing")
    node = body
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return body


@pytest.mark.parametrize("path,value", [
    (("fleet", "available_vessels"), -1),
    (("fleet", "available_vessels"), 3.5),
    (("fleet", "min_speed_knots"), 0),
    (("fleet", "min_speed_knots"), 23),            # > max speed
    (("economics", "fuel_price_usd_per_tonne"), 0),
    (("economics", "deployment_cost_usd_per_vessel_week"), -5),
    (("services", 0, "legs", "eastbound", "suez"), -100),
    (("services", 0, "legs", "westbound"), {"suez": 11000}),   # cape leg required by both scenarios
    (("services", 0, "port_days"), -1),
    (("services", 1, "service_id"), "S1"),          # duplicate id
    (("scenario",), "panama"),
    (("unexpected_field",), 1),
])
def test_validation_errors_return_422(path, value):
    assert client.post("/api/optimize", json=_mutate(path, value)).status_code == 422


def test_enabled_rule_with_missing_service_value_is_422():
    body = defaults(scenario="mixed_routing")
    body["rules"]["minimum_schedule_buffer"]["days_by_service"].pop("FAL5")
    assert client.post("/api/optimize", json=body).status_code == 422
    body["rules"]["minimum_schedule_buffer"]["enabled"] = False  # disabled rule is not checked
    assert client.post("/api/optimize", json=body).status_code == 200


def test_malformed_json_is_422():
    r = client.post("/api/optimize", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_verification_failure_returns_500_without_solution(monkeypatch):
    import app.solver as solver_mod
    monkeypatch.setattr(solver_mod, "verify", lambda *a, **k: ["forced violation"])
    r = client.post("/api/optimize", json=defaults(scenario="mixed_routing"))
    assert r.status_code == 500
    assert r.json()["error"] == "verification_failed" and "metrics" not in r.json()


def test_scenario_uses_sum_of_its_directional_legs():
    body = defaults(scenario="mixed_routing")
    j = client.post("/api/optimize", json=body).json()
    svc = body["services"][0]
    sailing = j["services"][0]["sailing_days"]
    speed = j["services"][0]["speed_knots"]
    expected_nm = svc["legs"]["westbound"]["cape"] + svc["legs"]["eastbound"]["suez"]
    assert sailing * 24 * speed == pytest.approx(expected_nm)


def test_compare_returns_fixed_fleet_impact():
    j = client.post("/api/compare", json=defaults()).json()
    a = j["a"]["metrics"]["total_cost_usd_week"]
    assert j["fixed_fleet_impact_usd_week"] == pytest.approx(j["b_fixed"]["metrics"]["total_cost_usd_week"] - a)
    body = defaults()
    body["fleet"]["available_vessels"] = 50
    body["fleet"]["max_speed_knots"] = 14.0
    assert client.post("/api/compare", json=body).json()["fixed_fleet_impact_usd_week"] is None


def test_frontend_files_are_revalidated():
    for path in ["/", "/css/styles.css", "/js/app.js"]:
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
