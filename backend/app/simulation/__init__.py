"""Simulated UAV flight, buried-object scenarios and sensor readings.

Nothing here talks to hardware: it stands in for the UAV and its payload so
the rest of the system can be developed and evaluated without them.
"""

from .scenario import SOIL_PROFILES, TARGET_KINDS, BuriedObject, ObjectKind, Scenario, SoilProfile
from .world import DEMO_AREA, Simulation, SimulationConfig, SurveyPlan, build_simulation, plan_survey

__all__ = [
    "DEMO_AREA",
    "SOIL_PROFILES",
    "TARGET_KINDS",
    "BuriedObject",
    "ObjectKind",
    "Scenario",
    "Simulation",
    "SimulationConfig",
    "SoilProfile",
    "SurveyPlan",
    "build_simulation",
    "plan_survey",
]
