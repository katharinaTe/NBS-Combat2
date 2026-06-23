#!/usr/bin/env python
"""Compute our full-year indicators and rank them against the six Combat teams
with TOPSIS (the organisers' ranking method).

Reads the full-year baseline ``.rpt`` and our candidate ``.rpt``, derives the
seven indicators (cost & biodiversity exact from the solution; the five
hydraulic/quality indicators as deltas vs the baseline), appends our row to the
teams' published indicators, and reports the TOPSIS ranking.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat.combat_data import load_limits, parse_subcatchment_geometry
from nbscombat.combat_model import parse_rpt
from nbscombat.combat_optimize import competition_solution
from nbscombat.combat_report import topsis, INDICATORS

# Published team indicators: cost, biodiversity, flood, evap, wwtp, cso, tss.
TEAMS = {
    "Team 1": [648895, 1251, 0.297, 8.824, 6.318, 25.125, 1986.598],
    "Team 2": [649030.1243, 1207, 0.288, 9.294, 6.71, 16.762, 1324.843],
    "Team 3": [627743.5, 974, 0.295, 6.678, 7.567, 15.942, 1796.379],
    "Team 4": [639352, 1269, 0.297, 8.448, 4.343, 24.359, 1889.238],
    "Team 5": [626695.07, 1212.91, 0.295, 8.067, -2.084, 22.328, 1742.657],
    "Team 6": [640019.71, 0, 0.184, 5.155, -0.644, 10.692, 819.523],
}

BASE_RPT = ROOT / "data/official/Case_study.rpt"
CAND_RPT = ROOT / "results_combat/runs_fy_cand/cand.rpt"


def main():
    base = parse_rpt(BASE_RPT.read_text(), cost=0, biodiversity=0)
    cand = parse_rpt(CAND_RPT.read_text(), cost=0, biodiversity=0)

    lim = load_limits(ROOT / "data/official/implementation_details.xlsx")
    geom = parse_subcatchment_geometry(ROOT / "data/official/Case_study.inp")
    sol = competition_solution(lim, geom, bio_target=1270, green_cap=40)

    ours = [
        sol.total_cost(),
        sol.biodiversity(),
        base.flood_volume - cand.flood_volume,     # flood reduction
        cand.evaporation - base.evaporation,        # evaporation gain
        cand.wwtp_volume - base.wwtp_volume,        # WWTP increase
        base.cso_volume - cand.cso_volume,          # CSO reduction
        base.cso_tss - cand.cso_tss,                # TSS reduction
    ]

    print("Full-year baseline:  flood=%.3f evap=%.3f wwtp=%.3f cso=%.3f tss=%.1f"
          % (base.flood_volume, base.evaporation, base.wwtp_volume,
             base.cso_volume, base.cso_tss))
    print("Full-year candidate: flood=%.3f evap=%.3f wwtp=%.3f cso=%.3f tss=%.1f\n"
          % (cand.flood_volume, cand.evaporation, cand.wwtp_volume,
             cand.cso_volume, cand.cso_tss))

    entrants = dict(TEAMS)
    entrants["OURS"] = ours
    names = list(entrants)
    M = np.array([entrants[n] for n in names], dtype=float)
    scores = topsis(M)
    order = np.argsort(-scores)

    cols = list(INDICATORS.keys())
    print("Indicators (cost, biodiversity, flood, evap, wwtp, cso, tss):")
    print(f"  {'entrant':8s} " + " ".join(f"{c[:8]:>9s}" for c in cols))
    for n in names:
        row = entrants[n]
        print(f"  {n:8s} " + " ".join(f"{v:>9.2f}" for v in row))

    print("\n=== TOPSIS ranking (organisers' method, equal weights) ===")
    for rank, i in enumerate(order, 1):
        star = "  <== OURS" if names[i] == "OURS" else ""
        print(f"  {rank}. {names[i]:8s} {scores[i]:.4f}{star}")

    our_rank = [names[i] for i in order].index("OURS") + 1
    print(f"\nOur position: #{our_rank} of {len(names)}")
    (ROOT / "results_combat/teams_comparison.txt").write_text(
        "\n".join(f"{names[i]}: {scores[i]:.4f}" for i in order))


if __name__ == "__main__":
    main()
