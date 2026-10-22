"""Independent check of a selected plan against the original model (01 §11.2).

Deliberately re-derives every quantity from the raw inputs instead of
reusing modeling.py helpers, so a bug in the coefficient code cannot hide
itself here.
"""
from __future__ import annotations

from app.modeling import Option, ScenarioProblem

REL_TOL = 1e-6
TIME_TOL = 1e-6  # days


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


def verify(problem: ScenarioProblem, plan: dict[str, Option], total_cost: float) -> list[str]:
    """Return a list of violations; empty means the plan is valid."""
    v: list[str] = []
    routes = {r.service_id: r for r in problem.services}

    if set(plan) != set(routes):  # C1: exactly one option per service
        v.append(f"plan services {sorted(plan)} != model services {sorted(routes)}")
        return v

    allocated = sum(o.n for o in plan.values())
    if allocated > problem.available_vessels:  # C2
        v.append(f"allocated {allocated} vessels > available {problem.available_vessels}")

    total = 0.0
    for sid, o in plan.items():
        r = routes[sid]
        n, speed = o.n, o.speed
        if not isinstance(n, int) or n < 1:
            v.append(f"{sid}: invalid vessel count {n}")
            continue
        if speed < problem.min_speed_knots - 1e-9 or speed > problem.max_speed_knots + 1e-9:  # C5
            v.append(f"{sid}: speed {speed:.4f} kn outside [{problem.min_speed_knots}, {problem.max_speed_knots}]")

        sailing = r.round_trip_nm / (24.0 * speed)
        buffer = problem.buffer_days.get(sid, 0.0)
        if sailing + r.port_days + buffer > 7 * n + TIME_TOL:  # C4 + C7
            v.append(f"{sid}: sailing {sailing:.3f} + port {r.port_days} + buffer {buffer} d > rotation {7 * n} d")
        tmax = problem.max_cycle_days.get(sid)
        if tmax is not None and sailing + r.port_days > tmax + TIME_TOL:  # C8
            v.append(f"{sid}: active cycle {sailing + r.port_days:.3f} d > max round trip {tmax} d")
        cap = problem.max_fleet.get(sid)
        if cap is not None and n > cap:  # C6
            v.append(f"{sid}: {n} vessels > cap {cap}")

        fuel = problem.fuel_price * problem.fuel_coeff * r.round_trip_nm * speed ** 2
        deploy = problem.deployment_cost * n
        if not _close(o.fuel_cost_week, fuel):
            v.append(f"{sid}: fuel cost {o.fuel_cost_week:.2f} != recomputed {fuel:.2f}")
        if not _close(o.deployment_cost_week, deploy):
            v.append(f"{sid}: deployment cost {o.deployment_cost_week:.2f} != recomputed {deploy:.2f}")
        if not _close(o.total_cost_week, fuel + deploy):
            v.append(f"{sid}: total cost {o.total_cost_week:.2f} != recomputed {fuel + deploy:.2f}")
        total += fuel + deploy

    if not _close(total_cost, total):
        v.append(f"objective {total_cost:.2f} != recomputed total {total:.2f}")
    return v
