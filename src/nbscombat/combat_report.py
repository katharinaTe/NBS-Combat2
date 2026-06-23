"""Indicator accounting, TOPSIS ranking, and reporting for the NBS Combat.

The Combat ranks teams with TOPSIS over seven indicators. We use the same method
to compare our own strategy variants and choose the recommended submission, and
to report every indicator as a change versus the no-NBS baseline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

from .combat_model import CombatKPIs

# Indicator name -> direction ("max" is better, "min" is better).
INDICATORS = {
    "cost": "min",
    "biodiversity": "max",
    "flood_reduction": "max",      # dVF
    "evaporation_gain": "max",     # dE
    "wwtp_increase": "max",        # dV_WWTP
    "cso_reduction": "max",        # dV_CSO
    "tss_reduction": "max",        # dM_TSS
}


@dataclass
class Indicators:
    cost: float
    biodiversity: float
    flood_reduction: float
    evaporation_gain: float
    wwtp_increase: float
    cso_reduction: float
    tss_reduction: float

    def as_row(self) -> List[float]:
        return [self.cost, self.biodiversity, self.flood_reduction,
                self.evaporation_gain, self.wwtp_increase,
                self.cso_reduction, self.tss_reduction]


def indicators_from_kpis(kpi: CombatKPIs, base: CombatKPIs) -> Indicators:
    """Convert raw KPIs + baseline into the seven ranked indicators (Eq. 4-8)."""
    return Indicators(
        cost=kpi.cost,
        biodiversity=kpi.biodiversity,
        flood_reduction=base.flood_volume - kpi.flood_volume,      # dVF
        evaporation_gain=kpi.evaporation - base.evaporation,       # dE
        wwtp_increase=kpi.wwtp_volume - base.wwtp_volume,          # dV_WWTP
        cso_reduction=base.cso_volume - kpi.cso_volume,            # dV_CSO
        tss_reduction=base.cso_tss - kpi.cso_tss,                  # dM_TSS
    )


def topsis(matrix: np.ndarray, weights: np.ndarray = None) -> np.ndarray:
    """Classic TOPSIS closeness scores for rows (higher = better)."""
    cols = list(INDICATORS.values())
    n_ind = matrix.shape[1]
    if weights is None:
        weights = np.ones(n_ind) / n_ind
    weights = weights / weights.sum()

    # Vector normalisation (guard zero columns).
    norm = np.linalg.norm(matrix, axis=0)
    norm = np.where(norm > 1e-12, norm, 1.0)
    V = matrix / norm * weights

    ideal = np.empty(n_ind)
    anti = np.empty(n_ind)
    for j, direction in enumerate(cols):
        if direction == "max":
            ideal[j], anti[j] = V[:, j].max(), V[:, j].min()
        else:
            ideal[j], anti[j] = V[:, j].min(), V[:, j].max()
    d_best = np.linalg.norm(V - ideal, axis=1)
    d_worst = np.linalg.norm(V - anti, axis=1)
    denom = np.where(d_best + d_worst > 1e-12, d_best + d_worst, 1.0)
    return d_worst / denom


def rank_variants(indicators: Dict[str, Indicators],
                  weights: np.ndarray = None):
    names = list(indicators.keys())
    matrix = np.array([indicators[n].as_row() for n in names], dtype=float)
    scores = topsis(matrix, weights)
    order = np.argsort(-scores)
    return [(names[i], scores[i]) for i in order]


def write_report(path: Path, *, baseline: CombatKPIs,
                 variant_kpis: Dict[str, CombatKPIs],
                 indicators: Dict[str, Indicators],
                 ranking, recommended: str, summaries: Dict[str, dict],
                 window: str = "full 2018 series"):
    lines = []
    a = lines.append
    a("# NBS Combat - Optimised Solution (official case study)\n")
    a(f"Seven indicators ranked by TOPSIS, evaluated with SWMM 5.2 on the "
      f"**{window}**. Cost and biodiversity are period-independent; the five "
      f"hydraulic/quality indicators below are computed on this window and used "
      f"to *rank* the strategy variants. The organisers score the submitted "
      f"solution on the full year.\n")

    a("## Baseline (no NBS)\n")
    a(f"- Flooding loss V_F: **{baseline.flood_volume:,.3f}** (10⁶ L)")
    a(f"- Evaporation loss E: **{baseline.evaporation:,.3f}**")
    a(f"- WWTP inflow volume: **{baseline.wwtp_volume:,.3f}** (10⁶ L)")
    a(f"- CSO overflow volume V_CSO: **{baseline.cso_volume:,.3f}** (10⁶ L)")
    a(f"- CSO TSS load M_TSS: **{baseline.cso_tss:,.1f}** (kg)\n")

    a("## Strategy variants - seven indicators\n")
    a("| Variant | Cost € | Biodiv. m² | ΔV_F flood↓ | ΔE evap↑ | "
      "ΔWWTP↑ | ΔCSO↓ | ΔTSS↓ kg | TOPSIS |")
    a("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    score_of = dict(ranking)
    for name in [r[0] for r in ranking]:
        ind = indicators[name]
        star = " ⭐" if name == recommended else ""
        a(f"| {name}{star} | {ind.cost:,.0f} | {ind.biodiversity:,.0f} | "
          f"{ind.flood_reduction:,.3f} | {ind.evaporation_gain:,.3f} | "
          f"{ind.wwtp_increase:,.3f} | {ind.cso_reduction:,.3f} | "
          f"{ind.tss_reduction:,.1f} | {score_of[name]:.3f} |")
    a("")
    a(f"**Recommended submission: `{recommended}`** "
      "(highest TOPSIS across the seven indicators).\n")

    a("## Recommended solution composition\n")
    s = summaries.get(recommended, {})
    a(f"- Total cost: €{s.get('cost', 0):,.0f} of €650,000 budget")
    a(f"- Biodiversity indicator: {s.get('biodiversity', 0):,.1f} m²")
    a(f"- Interventions: {s.get('interventions', 0)} across "
      f"{s.get('subcatchments', 0)} sub-catchments")
    a("- Area by NBS type (m²):")
    for k, v in s.get("area_by_type", {}).items():
        a(f"    - {k}: {v:,.1f}")
    a("")
    path.write_text("\n".join(lines))
