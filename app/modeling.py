"""Per-option preprocessing for the fleet allocation model (01 §5).

For every service s and fleet size n = 1..F this computes the option's
speed, sailing time and weekly cost. These numbers are the coefficients of
the linear 0-1 model built in solver.py. Nothing here decides feasibility
for the optimization; the solver does that. The helpers at the bottom
(time_rule_violations, infeasibility_diagnostics) are used to evaluate
B_fixed and to *explain* an INFEASIBLE solver status after the fact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

HOURS_PER_DAY = 24.0
DAYS_PER_WEEK = 7
TIME_TOL_DAYS = 1e-9  # tolerance on time constraints (exact-v_max options)
EARTH_RADIUS_NM = 3440.065


def polyline_nm(points: list[list]) -> float:
    """Great-circle length of a waypoint path; points are [lat, lon, (optional name)]."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        total += 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(h))
    return total


def scenario_round_trip_nm(legs: dict[str, dict[str, float]], routing: dict[str, str]) -> float:
    """D_s = westbound leg + eastbound leg, each taken via the variant the scenario uses.

    legs: {"westbound": {"cape": nm}, "eastbound": {"suez": nm, "cape": nm}}
    routing: {"westbound": "cape", "eastbound": "suez"}
    """
    return sum(legs[direction][variant] for direction, variant in routing.items())


@dataclass(frozen=True)
class ServiceRoute:
    """One service's inputs under one scenario."""
    service_id: str
    round_trip_nm: float  # D_s
    port_days: float      # P_s


@dataclass(frozen=True)
class ScenarioProblem:
    """Everything needed to build and solve one scenario."""
    scenario: str
    services: list[ServiceRoute]
    available_vessels: int            # F
    min_speed_knots: float            # v_min
    max_speed_knots: float            # v_max
    fuel_coeff: float                 # c, tonnes per nm per knot^2
    fuel_price: float                 # p, USD/tonne
    deployment_cost: float            # h, USD/vessel/week
    buffer_days: dict[str, float] = field(default_factory=dict)  # B_eff_s; missing = 0 (C7 off)
    max_cycle_days: dict[str, float] = field(default_factory=dict)  # Tmax_s; missing = C8 off
    max_fleet: dict[str, int] = field(default_factory=dict)  # M_s; missing = C6 off

    def buffer(self, service_id: str) -> float:
        return self.buffer_days.get(service_id, 0.0)

    def tmax(self, service_id: str) -> float | None:
        return self.max_cycle_days.get(service_id)


@dataclass(frozen=True)
class Option:
    """Coefficients of option (s, n)."""
    service_id: str
    n: int
    required_speed: float   # max(v_min, v_freq, v_cycle); may be > v_max or inf
    speed: float            # v_opt = min(v_max, required_speed)
    speed_binding: str      # min_speed | frequency | max_cycle | max_speed_cap
    sailing_days: float
    active_cycle_days: float
    rotation_days: float
    slack_days: float
    fuel_tonnes_week: float
    fuel_cost_week: float
    deployment_cost_week: float
    total_cost_week: float


def fuel_coefficient(reference_speed_knots: float, reference_fuel_tonnes_per_day: float) -> float:
    """c such that per-nm fuel is c*v^2 and daily fuel at v_ref is f_ref."""
    return reference_fuel_tonnes_per_day / (HOURS_PER_DAY * reference_speed_knots ** 3)


def frequency_speed(round_trip_nm: float, port_days: float, buffer_days: float, n: int) -> float:
    """Minimum speed for weekly departures with n ships; inf if no speed works."""
    sailing_window = DAYS_PER_WEEK * n - port_days - buffer_days
    if sailing_window <= 0:
        return math.inf
    return round_trip_nm / (HOURS_PER_DAY * sailing_window)


def cycle_speed(round_trip_nm: float, port_days: float, tmax_days: float | None) -> float:
    """Minimum speed for the max round-trip time; 0 if C8 is off, inf if impossible."""
    if tmax_days is None:
        return 0.0
    sailing_window = tmax_days - port_days
    if sailing_window <= 0:
        return math.inf
    return round_trip_nm / (HOURS_PER_DAY * sailing_window)


def build_option(problem: ScenarioProblem, route: ServiceRoute, n: int) -> Option:
    sid = route.service_id
    v_min, v_max = problem.min_speed_knots, problem.max_speed_knots
    v_freq = frequency_speed(route.round_trip_nm, route.port_days, problem.buffer(sid), n)
    v_cycle = cycle_speed(route.round_trip_nm, route.port_days, problem.tmax(sid))
    required = max(v_min, v_freq, v_cycle)
    speed = min(v_max, required)

    if required > v_max:
        binding = "max_speed_cap"
    elif required == v_min:
        binding = "min_speed"
    elif v_freq >= v_cycle:
        binding = "frequency"
    else:
        binding = "max_cycle"

    sailing = route.round_trip_nm / (HOURS_PER_DAY * speed)
    active = sailing + route.port_days
    rotation = float(DAYS_PER_WEEK * n)
    fuel_t = problem.fuel_coeff * route.round_trip_nm * speed ** 2
    fuel_usd = problem.fuel_price * fuel_t
    deploy_usd = problem.deployment_cost * n
    return Option(
        service_id=sid, n=n, required_speed=required, speed=speed, speed_binding=binding,
        sailing_days=sailing, active_cycle_days=active, rotation_days=rotation,
        slack_days=rotation - active, fuel_tonnes_week=fuel_t, fuel_cost_week=fuel_usd,
        deployment_cost_week=deploy_usd, total_cost_week=fuel_usd + deploy_usd,
    )


def build_options(problem: ScenarioProblem) -> dict[str, dict[int, Option]]:
    """All options n = 1..F for every service (no pre-filtering)."""
    return {
        route.service_id: {n: build_option(problem, route, n)
                           for n in range(1, problem.available_vessels + 1)}
        for route in problem.services
    }


def time_rule_violations(problem: ScenarioProblem, route: ServiceRoute, opt: Option) -> list[str]:
    """C4/C7 and C8 checks for one option, mirroring the solver rows."""
    sid = route.service_id
    out = []
    buf = problem.buffer(sid)
    if opt.sailing_days + route.port_days + buf - opt.rotation_days > TIME_TOL_DAYS:
        needed = opt.required_speed
        speed_txt = "no speed works" if math.isinf(needed) else f"needs {needed:.1f} kn"
        out.append(
            f"{sid}: {opt.n} vessels cannot keep weekly departures"
            f"{' with a ' + format(buf, 'g') + '-day buffer' if buf else ''} "
            f"({speed_txt}, max {problem.max_speed_knots:g} kn)"
        )
    tmax = problem.tmax(sid)
    if tmax is not None and opt.sailing_days + route.port_days - tmax > TIME_TOL_DAYS:
        if tmax <= route.port_days:
            out.append(f"{sid}: max round-trip time {tmax:g} d is not above port time {route.port_days:g} d")
        else:
            v_cycle = cycle_speed(route.round_trip_nm, route.port_days, tmax)
            out.append(f"{sid}: max round-trip time {tmax:g} d needs {v_cycle:.1f} kn "
                       f"> max {problem.max_speed_knots:g} kn")
    return out


def infeasibility_diagnostics(problem: ScenarioProblem,
                              options: dict[str, dict[int, Option]]) -> dict:
    """Explain an INFEASIBLE solver status (explanation only, not a decision)."""
    routes = {r.service_id: r for r in problem.services}
    min_vessels: dict[str, int | None] = {}
    reasons: list[str] = []
    for sid, opts in options.items():
        feasible_n = [n for n, o in opts.items() if not time_rule_violations(problem, routes[sid], o)]
        if not feasible_n:
            min_vessels[sid] = None
            worst = time_rule_violations(problem, routes[sid], opts[problem.available_vessels])
            reasons.append(f"{sid}: no fleet size up to {problem.available_vessels} works — " +
                           "; ".join(v.split(': ', 1)[1] for v in worst))
            continue
        n_min = min(feasible_n)
        min_vessels[sid] = n_min
        cap = problem.max_fleet.get(sid)
        if cap is not None and cap < n_min:
            reasons.append(f"{sid}: fleet cap {cap} is below the minimum {n_min} vessels needed")

    known = [n for n in min_vessels.values() if n is not None]
    total_min = sum(known) if len(known) == len(min_vessels) else None
    if total_min is not None and total_min > problem.available_vessels:
        reasons.append(f"Minimum fleet needed is {total_min} vessels, "
                       f"only {problem.available_vessels} available")
    return {
        "min_vessels_by_service": min_vessels,
        "total_min_vessels": total_min,
        "available_vessels": problem.available_vessels,
        "reasons": reasons,
    }
