#!/usr/bin/env python
"""Evaluate a single retrofit design against the full design-storm suite.

Examples:
    # Baseline (no NBS):
    python scripts/evaluate_design.py --baseline

    # A specific design from a completed optimisation (row of pareto_decisions.csv):
    python scripts/evaluate_design.py --decisions results/pareto_decisions.csv --row 33
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat.swmm_model import SWMMModel, VERIFICATION_STORMS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inp", default=str(ROOT / "data/case_study/baseline.inp"))
    ap.add_argument("--baseline", action="store_true", help="evaluate the do-nothing case")
    ap.add_argument("--decisions", help="CSV of decision vectors (rows)")
    ap.add_argument("--row", type=int, default=0, help="row index in --decisions")
    args = ap.parse_args()

    model = SWMMModel(args.inp, storms=list(VERIFICATION_STORMS))

    if args.baseline or not args.decisions:
        x = np.zeros(model.n_var)
        label = "BASELINE (no NBS)"
    else:
        X = np.atleast_2d(np.loadtxt(args.decisions, delimiter=","))
        x = X[args.row]
        label = f"{Path(args.decisions).name} row {args.row}"

    kpi = model.evaluate(x)
    print(f"=== {label} ===")
    print(f"  Lifecycle cost:   EUR {kpi.cost:,.0f}")
    print(f"  Co-benefit index: {kpi.cobenefit:,.0f}")
    print(f"  NBS footprint:    {kpi.footprint:,.0f} m²")
    print(f"  Peak outfall:     {kpi.peak_outflow:.2f} m³/s")
    print("  Flooding by storm (m³):")
    for s, v in kpi.flood_by_storm.items():
        print(f"    {s:6s}: {v:,.1f}")
    rows = model.placement_table(x)
    if rows:
        print(f"  Interventions: {len(rows)} (top 8 by cost)")
        for r in sorted(rows, key=lambda r: -r["lifecycle_eur"])[:8]:
            print(f"    {r['subcatchment']:4s} {r['type']:3s} "
                  f"{r['area_m2']:8.0f} m²  EUR {r['lifecycle_eur']:,.0f}")


if __name__ == "__main__":
    main()
