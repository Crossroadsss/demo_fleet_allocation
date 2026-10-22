import pytest

from app import data
from app.modeling import polyline_nm, scenario_round_trip_nm


def test_scenarios_define_directional_routing():
    assert data.SCENARIOS["mixed_routing"]["routing"] == {"westbound": "cape", "eastbound": "suez"}
    assert data.SCENARIOS["full_cape"]["routing"] == {"westbound": "cape", "eastbound": "cape"}


def test_waypoint_geometry_matches_published_reference_distance():
    ref = data.REFERENCE_SHANGHAI_ROTTERDAM
    for variant in ("suez", "cape"):
        assert polyline_nm(ref[variant]) == pytest.approx(ref["published_nm"][variant], rel=0.05)


@pytest.mark.parametrize("svc", data.DEFAULT_INPUT["services"], ids=lambda s: s["service_id"])
def test_default_legs_equal_waypoint_lengths(svc):
    route = data.ROUTES[svc["service_id"]]
    for direction, variants in svc["legs"].items():
        for variant, nm in variants.items():
            assert nm == round(polyline_nm(route[direction][variant]))


@pytest.mark.parametrize("svc", data.DEFAULT_INPUT["services"], ids=lambda s: s["service_id"])
def test_round_trip_distance_per_scenario(svc):
    legs = svc["legs"]
    mixed = scenario_round_trip_nm(legs, data.SCENARIOS["mixed_routing"]["routing"])
    cape = scenario_round_trip_nm(legs, data.SCENARIOS["full_cape"]["routing"])
    assert mixed == legs["westbound"]["cape"] + legs["eastbound"]["suez"]
    assert cape == legs["westbound"]["cape"] + legs["eastbound"]["cape"]
    assert cape - mixed > 2500  # Cape eastbound is materially longer than Suez eastbound


@pytest.mark.parametrize("sid", ["FAL2", "FAL3", "FAL5"])
def test_directional_paths_connect_and_are_not_simple_reversals(sid):
    r = data.ROUTES[sid]
    wb = r["westbound"]["cape"]
    for variant, eb in r["eastbound"].items():
        assert eb[0][2] == wb[-1][2]   # eastbound starts at the westbound turnaround port
        assert eb[-1][2] == wb[0][2]   # and returns to the origin port
        assert [p[:2] for p in eb] != [p[:2] for p in reversed(wb)]


@pytest.mark.parametrize("sid", ["FAL2", "FAL3", "FAL5"])
def test_suez_variant_passes_suez_and_cape_variant_rounds_africa(sid):
    r = data.ROUTES[sid]
    def passes_suez(pts):
        return any(29.0 < p[0] < 31.6 and 32.0 < p[1] < 32.8 for p in pts)
    def rounds_cape(pts):
        return any(p[0] < -33.0 for p in pts)
    assert rounds_cape(r["westbound"]["cape"]) and not passes_suez(r["westbound"]["cape"])
    assert passes_suez(r["eastbound"]["suez"]) and not rounds_cape(r["eastbound"]["suez"])
    assert rounds_cape(r["eastbound"]["cape"]) and not passes_suez(r["eastbound"]["cape"])


def test_port_days_follow_port_call_count():
    for svc in data.DEFAULT_INPUT["services"]:
        calls = data._port_calls(svc["service_id"])
        assert svc["port_days"] == pytest.approx(data.PORT_DAYS_PER_CALL * len(calls))
    # published port-call counts: FAL2 10, FAL5 12
    assert len(data._port_calls("FAL2")) == 10
    assert data._port_calls("FAL5") == ["Qingdao", "Shanghai", "Ningbo", "Xiamen", "Yantian", "Singapore", "Felixstowe",
                                        "Zeebrugge", "Gdansk", "Wilhelmshaven", "Singapore", "Yantian"]


def test_default_services_and_fleet():
    assert [s["service_id"] for s in data.DEFAULT_INPUT["services"]] == ["FAL2", "FAL3", "FAL5"]
    published = sum(m["published_vessels_full_cape"] for m in data.SERVICE_META.values())
    assert data.DEFAULT_INPUT["fleet"]["available_vessels"] == published == 44
