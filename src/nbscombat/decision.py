"""Select a recommended design from the Pareto set via multi-criteria analysis.

Two complementary picks are returned:

* ``topsis``     -- best compromise across all objectives using TOPSIS with
                    user-supplied objective weights (the headline recommendation).
* ``budget``     -- cheapest non-dominated design that meets a flood-reduction
                    target (decision-maker view when a target service level is set).
"""
from __future__ import annotations

import numpy as np


def _normalize(F: np.ndarray) -> np.ndarray:
    """Min-max normalise each column to [0, 1] (0 = best since all minimised)."""
    lo = F.min(axis=0)
    span = np.where(F.max(axis=0) - lo > 1e-12, F.max(axis=0) - lo, 1.0)
    return (F - lo) / span


def topsis(F: np.ndarray, weights=(0.5, 0.3, 0.2)) -> int:
    """Return the index of the TOPSIS-optimal compromise (objectives minimised)."""
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    Z = _normalize(F) * w                       # weighted, lower is better
    ideal = Z.min(axis=0)
    anti = Z.max(axis=0)
    d_best = np.linalg.norm(Z - ideal, axis=1)
    d_worst = np.linalg.norm(Z - anti, axis=1)
    closeness = d_worst / np.where(d_best + d_worst > 1e-12, d_best + d_worst, 1.0)
    return int(np.argmax(closeness))


def knee_point(F2: np.ndarray) -> int:
    """Knee of a 2-objective (cost, flood) trade-off via max distance to the
    chord between the two anchor extremes."""
    pts = F2.copy()
    a, b = pts[pts[:, 0].argmin()], pts[pts[:, 1].argmin()]
    ab = b - a
    ab_norm = ab / (np.linalg.norm(ab) + 1e-12)
    # perpendicular distance of each point from the chord a-b
    rel = pts - a
    proj = (rel @ ab_norm)[:, None] * ab_norm
    dist = np.linalg.norm(rel - proj, axis=1)
    return int(np.argmax(dist))


def budget_optimal(F: np.ndarray, baseline_flood: float,
                   target_reduction: float = 0.9) -> int | None:
    """Cheapest design achieving at least ``target_reduction`` flood cut.

    F columns: [flood, cost, -cobenefit]. Returns None if no design qualifies.
    """
    target_flood = baseline_flood * (1.0 - target_reduction)
    mask = F[:, 0] <= target_flood
    if not mask.any():
        return None
    idx = np.where(mask)[0]
    return int(idx[F[idx, 1].argmin()])
