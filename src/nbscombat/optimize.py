"""NSGA-II driver for the NBS retrofit problem."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from .problem import NBSRetrofitProblem
from .swmm_model import SWMMModel


@dataclass
class OptResult:
    X: np.ndarray          # decision vectors of the non-dominated set
    F: np.ndarray          # objectives [flood, cost, -cobenefit]
    n_evals: int


def _seed_population(n_var: int, pop_size: int, rng) -> np.ndarray:
    """Initial population spanning sparse/cheap to dense/expensive retrofits.

    Plain LHS averages ~0.5 per variable, which decodes to large, costly designs
    and leaves the affordable end of the Pareto front empty.  Each individual is
    given a random sparsity ``p`` (fraction of active interventions) and a random
    intensity scale ``s`` so the seed set covers the whole cost range -- from a
    handful of small NBS to a fully greened catchment.
    """
    X = np.zeros((pop_size, n_var))
    X[0] = 0.0                                  # do-nothing anchor
    for i in range(1, pop_size):
        p = rng.uniform(0.05, 1.0)              # activation probability
        s = rng.uniform(0.05, 1.0)              # intensity scale
        mask = rng.random(n_var) < p
        X[i] = mask * rng.random(n_var) * s
    return X


def run_nsga2(model: SWMMModel, *, pop_size: int = 60, n_gen: int = 40,
              budget: float | None = None, seed: int = 1,
              verbose: bool = True) -> OptResult:
    problem = NBSRetrofitProblem(model, budget=budget)
    rng = np.random.default_rng(seed)
    sampling = _seed_population(model.n_var, pop_size, rng)
    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=sampling,
        crossover=SBX(prob=0.9, eta=15),
        mutation=PM(eta=20),
        eliminate_duplicates=True,
    )
    termination = get_termination("n_gen", n_gen)
    res = minimize(problem, algorithm, termination, seed=seed,
                   save_history=False, verbose=verbose)

    X = np.atleast_2d(res.X)
    F = np.atleast_2d(res.F)
    # Always include the do-nothing anchor (cost 0, baseline flood) for context.
    zero = np.zeros((1, model.n_var))
    kpi0 = model.evaluate(zero[0])
    F0 = np.array([[kpi0.flood_weighted, kpi0.cost, -kpi0.cobenefit]])
    X = np.vstack([X, zero])
    F = np.vstack([F, F0])
    return OptResult(X=X, F=F, n_evals=res.algorithm.evaluator.n_eval)
