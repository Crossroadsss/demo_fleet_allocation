"""Pydantic request models with cross-field validation (02 §3)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.data import INPUT_BOUNDS as B
from app.data import SCENARIOS
from app.modeling import ScenarioProblem, ServiceRoute, fuel_coefficient, scenario_round_trip_nm

ScenarioId = Literal["mixed_routing", "full_cape"]
RouteVariant = Literal["suez", "cape"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LegsIn(_Strict):
    """Sailing distance (nm) per direction and route variant; westbound = Asia -> Europe."""
    westbound: dict[RouteVariant, float]
    eastbound: dict[RouteVariant, float]

    @model_validator(mode="after")
    def _complete_and_in_range(self):
        lo, hi = B["leg_nm"]["min"], B["leg_nm"]["max"]
        for scen_id, scen in SCENARIOS.items():
            for direction, variant in scen["routing"].items():
                if variant not in getattr(self, direction):
                    raise ValueError(f"{direction} distance via {variant} is required by scenario {scen_id}")
        for direction in ("westbound", "eastbound"):
            for variant, nm in getattr(self, direction).items():
                if not lo <= nm <= hi:
                    raise ValueError(f"{direction} {variant} distance {nm} outside [{lo}, {hi}] nm")
        return self


class ServiceIn(_Strict):
    service_id: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(default="", max_length=80)
    legs: LegsIn
    port_days: float = Field(ge=B["port_days"]["min"], le=B["port_days"]["max"])


class FleetIn(_Strict):
    available_vessels: int = Field(ge=B["available_vessels"]["min"], le=B["available_vessels"]["max"])
    min_speed_knots: float = Field(gt=0, le=B["speed_knots"]["max"])
    max_speed_knots: float = Field(gt=0, le=B["speed_knots"]["max"])
    reference_speed_knots: float = Field(gt=0, le=B["speed_knots"]["max"])
    reference_fuel_tonnes_per_day: float = Field(ge=B["reference_fuel_tonnes_per_day"]["min"],
                                                 le=B["reference_fuel_tonnes_per_day"]["max"])

    @model_validator(mode="after")
    def _speeds_ordered(self):
        if self.min_speed_knots > self.max_speed_knots:
            raise ValueError("min_speed_knots must be <= max_speed_knots")
        return self


class EconomicsIn(_Strict):
    fuel_price_usd_per_tonne: float = Field(ge=B["fuel_price_usd_per_tonne"]["min"],
                                            le=B["fuel_price_usd_per_tonne"]["max"])
    deployment_cost_usd_per_vessel_week: float = Field(ge=B["deployment_cost_usd_per_vessel_week"]["min"],
                                                       le=B["deployment_cost_usd_per_vessel_week"]["max"])


class FleetCapRule(_Strict):
    enabled: bool = False
    limits: dict[str, int] = Field(default_factory=dict)


class DaysRule(_Strict):
    enabled: bool = False
    days_by_service: dict[str, float] = Field(default_factory=dict)


class RulesIn(_Strict):
    max_fleet_per_service: FleetCapRule = Field(default_factory=FleetCapRule)
    minimum_schedule_buffer: DaysRule = Field(default_factory=DaysRule)
    maximum_round_trip_time: DaysRule = Field(default_factory=DaysRule)


def _check_rule_values(name: str, values: dict, ids: set[str], lo: float, hi: float) -> None:
    missing, unknown = ids - set(values), set(values) - ids
    if missing:
        raise ValueError(f"{name}: missing value for service(s) {sorted(missing)}")
    if unknown:
        raise ValueError(f"{name}: unknown service(s) {sorted(unknown)}")
    for sid, val in values.items():
        if not lo <= val <= hi:
            raise ValueError(f"{name}: value {val} for {sid} outside [{lo}, {hi}]")


class ModelInput(_Strict):
    fleet: FleetIn
    economics: EconomicsIn
    services: list[ServiceIn] = Field(min_length=1, max_length=B["max_services"])
    rules: RulesIn = Field(default_factory=RulesIn)

    @model_validator(mode="after")
    def _cross_checks(self):
        ids = [s.service_id for s in self.services]
        if len(set(ids)) != len(ids):
            raise ValueError("service_id values must be unique")
        idset = set(ids)
        r = self.rules
        if r.max_fleet_per_service.enabled:
            bounds = B["max_fleet_per_service"]
            _check_rule_values("max_fleet_per_service", r.max_fleet_per_service.limits, idset,
                               bounds["min"], bounds["max"])
        if r.minimum_schedule_buffer.enabled:
            bounds = B["minimum_schedule_buffer_days"]
            _check_rule_values("minimum_schedule_buffer", r.minimum_schedule_buffer.days_by_service, idset,
                               bounds["min"], bounds["max"])
        if r.maximum_round_trip_time.enabled:
            bounds = B["maximum_round_trip_days"]
            _check_rule_values("maximum_round_trip_time", r.maximum_round_trip_time.days_by_service, idset,
                               bounds["min"], bounds["max"])
        return self

    @staticmethod
    def round_trip_nm(service: ServiceIn, scenario: ScenarioId) -> float:
        legs = {"westbound": service.legs.westbound, "eastbound": service.legs.eastbound}
        return scenario_round_trip_nm(legs, SCENARIOS[scenario]["routing"])

    def to_problem(self, scenario: ScenarioId) -> ScenarioProblem:
        r = self.rules
        return ScenarioProblem(
            scenario=scenario,
            services=[ServiceRoute(s.service_id, self.round_trip_nm(s, scenario), s.port_days) for s in self.services],
            available_vessels=self.fleet.available_vessels,
            min_speed_knots=self.fleet.min_speed_knots,
            max_speed_knots=self.fleet.max_speed_knots,
            fuel_coeff=fuel_coefficient(self.fleet.reference_speed_knots, self.fleet.reference_fuel_tonnes_per_day),
            fuel_price=self.economics.fuel_price_usd_per_tonne,
            deployment_cost=self.economics.deployment_cost_usd_per_vessel_week,
            buffer_days=dict(r.minimum_schedule_buffer.days_by_service) if r.minimum_schedule_buffer.enabled else {},
            max_cycle_days=dict(r.maximum_round_trip_time.days_by_service) if r.maximum_round_trip_time.enabled else {},
            max_fleet=dict(r.max_fleet_per_service.limits) if r.max_fleet_per_service.enabled else {},
        )


class OptimizeRequest(ModelInput):
    scenario: ScenarioId


class CompareRequest(ModelInput):
    pass
