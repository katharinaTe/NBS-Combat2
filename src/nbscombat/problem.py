"""Multi-objective optimisation problem for NBS retrofit (pymoo)."""
from __future__ import annotations

import numpy as np
from pymoo.core.problem import ElementwiseProblem

from .swmm_model import SWMMModel


class NBSRetrofitProblem(ElementwiseProblem):
    """Decision: per (sub-catchment, NBS-type) area fraction in [0, 1].

    Objectives (all minimised):
        f1 = weighted design-storm flooding volume (m3)   -- hydraulic performance
        f2 = lifecycle cost (EUR)                          -- affordability
        f3 = - aggregated co-benefit index                 -- amenity/biodiversity/...

    Optional constraint:
        g1 = cost - budget <= 0                            -- if a budget is given
    """

    def __init__(self, model: SWMMModel, budget: float | None = None):
        self.model = model
        self.budget = budget
        super().__init__(
            n_var=model.n_var,
            n_obj=3,
            n_ieq_constr=1 if budget is not None else 0,
            xl=0.0,
            xu=1.0,
        )

    def _evaluate(self, x, out, *args, **kwargs):
        kpi = self.model.evaluate(x)
        out["F"] = np.array([kpi.flood_weighted, kpi.cost, -kpi.cobenefit])
        if self.budget is not None:
            out["G"] = np.array([kpi.cost - self.budget])
