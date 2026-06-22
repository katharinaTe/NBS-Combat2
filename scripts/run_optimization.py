#!/usr/bin/env python
"""End-to-end NBS Combat solver.

Optimise the placement of Nature-Based Solutions across an urban drainage
catchment to jointly minimise design-storm flooding and lifecycle cost while
maximising co-benefits, then select and report a recommended retrofit.

Usage:
    python scripts/run_optimization.py --quick      # fast demo (~1-2 min)
    python scripts/run_optimization.py --full       # competition-grade run
    python scripts/run_optimization.py --pop 80 --gen 60 --budget 5e6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat import decision, reporting          # noqa: E402
from nbscombat.optimize import run_nsga2            # noqa: E402
from nbscombat.swmm_model import (DEFAULT_STORMS, VERIFICATION_STORMS,  # noqa: E402
                                  SWMMModel)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inp", default=str(ROOT / "data/case_study/baseline.inp"))
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--pop", type=int, default=60)
    ap.add_argument("--gen", type=int, default=40)
    ap.add_argument("--budget", type=float, default=None,
                    help="optional lifecycle-cost cap in EUR")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="small fast run")
    ap.add_argument("--full", action="store_true", help="larger thorough run")
    ap.add_argument("--weights", default="0.5,0.3,0.2",
                    help="TOPSIS weights for flood,cost,cobenefit")
    args = ap.parse_args()

    if args.quick:
        args.pop, args.gen = 30, 18
    if args.full:
        args.pop, args.gen = 100, 70

    results = Path(args.results)
    results.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Loading model: {args.inp}")
    model = SWMMModel(args.inp, storms=list(DEFAULT_STORMS))
    print(f"      {len(model.subcatchments)} sub-catchments, "
          f"{model.n_var} decision variables, palette={model.palette}")

    print(f"[2/5] NSGA-II  (pop={args.pop}, gen={args.gen}, budget={args.budget})")
    opt = run_nsga2(model, pop_size=args.pop, n_gen=args.gen,
                    budget=args.budget, seed=args.seed, verbose=True)
    print(f"      {opt.F.shape[0]} non-dominated designs, {opt.n_evals} evaluations")

    print("[3/5] Selecting recommended designs")
    weights = tuple(float(w) for w in args.weights.split(","))
    baseline_kpi = model.evaluate(np.zeros(model.n_var))
    i_topsis = decision.topsis(opt.F, weights=weights)
    i_knee = decision.knee_point(opt.F[:, :2])
    i_budget = decision.budget_optimal(opt.F, baseline_kpi.flood_weighted,
                                       target_reduction=0.9)
    picks = {"topsis": i_topsis, "knee": i_knee, "budget": i_budget}

    rec_kpi = model.evaluate(opt.X[i_topsis])
    rec_rows = model.placement_table(opt.X[i_topsis])
    picks_kpi = {name: (model.evaluate(opt.X[idx]) if idx is not None else None)
                 for name, idx in picks.items()}

    print("[4/5] Independent verification across full storm suite")
    verif_model = SWMMModel(args.inp, storms=list(VERIFICATION_STORMS))
    vk = verif_model.evaluate(opt.X[i_topsis])
    verification = {s: round(v, 1) for s, v in vk.flood_by_storm.items()}

    print("[5/5] Writing reports & figures")
    reporting.plot_pareto(opt.F, picks, results / "pareto_front.png")
    reporting.plot_flood_reduction(baseline_kpi.flood_by_storm,
                                   rec_kpi.flood_by_storm,
                                   results / "flood_reduction.png")
    reporting.write_design_csv(rec_rows, results / "recommended_design.csv")
    reporting.write_summary(
        results / "summary.md",
        model_name=Path(args.inp).name, n_var=model.n_var, n_evals=opt.n_evals,
        baseline_kpi=baseline_kpi, recommended_kpi=rec_kpi,
        recommended_rows=rec_rows, picks_kpi=picks_kpi, verification=verification)

    # Machine-readable Pareto set for downstream analysis / reproducibility.
    np.savetxt(results / "pareto_objectives.csv", opt.F, delimiter=",",
               header="flood_weighted_m3,cost_eur,neg_cobenefit", comments="")
    np.savetxt(results / "pareto_decisions.csv", opt.X, delimiter=",", comments="")
    (results / "run_config.json").write_text(json.dumps({
        "inp": args.inp, "pop": args.pop, "gen": args.gen,
        "budget": args.budget, "seed": args.seed, "weights": weights,
        "n_evals": opt.n_evals, "palette": model.palette,
    }, indent=2))

    flood_cut = 100 * (1 - rec_kpi.flood_weighted / max(baseline_kpi.flood_weighted, 1e-9))
    print("\n=== RECOMMENDED SOLUTION (TOPSIS) ===")
    print(f"  Weighted flooding: {baseline_kpi.flood_weighted:,.0f} -> "
          f"{rec_kpi.flood_weighted:,.0f} m³  ({flood_cut:.1f}% cut)")
    print(f"  Lifecycle cost:    EUR {rec_kpi.cost:,.0f}")
    print(f"  Co-benefit index:  {rec_kpi.cobenefit:,.0f}")
    print(f"  NBS footprint:     {rec_kpi.footprint:,.0f} m²")
    print(f"  Reports written to {results}/")


if __name__ == "__main__":
    main()
