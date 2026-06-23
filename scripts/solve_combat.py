#!/usr/bin/env python
"""Solve the official UDM-2025 NBS Combat.

Builds rule-compliant, budget-feasible strategy variants with the static
cost-effectiveness optimiser (no SWMM), writes each as an official
``solutions.xlsx``, and -- with ``--validate`` -- evaluates them with the SWMM
engine over the full 2018 series, ranks them by TOPSIS over the seven Combat
indicators, and writes the recommended submission.

    # Fast: construct variants + write Excel solutions (no simulation)
    python scripts/solve_combat.py

    # Full: also run SWMM validation (parallel) and pick the TOPSIS winner
    python scripts/solve_combat.py --validate
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat.combat_data import load_limits, parse_subcatchment_geometry  # noqa: E402
from nbscombat.combat_model import Solution, parse_rpt                       # noqa: E402
from nbscombat.combat_optimize import greedy_solution, summarise            # noqa: E402
from nbscombat import combat_report                                          # noqa: E402

# Strategy variants: (name, kwargs for greedy_solution).
VARIANTS = {
    "capture":    dict(bio_target=0),
    "balanced":   dict(bio_target=300),
    "biodiverse": dict(bio_target=600),
    "thrifty":    dict(bio_target=300, budget=450_000.0),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inp", default=str(ROOT / "data/official/Case_study.inp"))
    ap.add_argument("--impl", default=str(ROOT / "data/official/implementation_details.xlsx"))
    ap.add_argument("--template", default=str(ROOT / "data/official/solutions_template.xlsx"))
    ap.add_argument("--baseline-rpt", default=str(ROOT / "data/official/Case_study.rpt"),
                    help="existing baseline .rpt to read baseline KPIs from")
    ap.add_argument("--results", default=str(ROOT / "results_combat"))
    ap.add_argument("--validate", action="store_true",
                    help="run full-year SWMM validation (slow)")
    ap.add_argument("--parallel", type=int, default=4)
    args = ap.parse_args()

    results = Path(args.results)
    results.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading case study constraints")
    limits = load_limits(args.impl)
    geom = parse_subcatchment_geometry(args.inp)
    print(f"      {len(limits)} sub-catchments, budget €650,000")

    print("[2/4] Constructing strategy variants (no simulation)")
    solutions = {name: greedy_solution(limits, geom, **kw)
                 for name, kw in VARIANTS.items()}
    summaries = {}
    for name, sol in solutions.items():
        errs = sol.validate(limits)
        s = summarise(sol)
        summaries[name] = s
        flag = "OK" if not errs else f"INVALID: {errs[:1]}"
        print(f"      {name:11s} cost €{s['cost']:>7,.0f}  biodiv {s['biodiversity']:>6.0f} m²"
              f"  interventions {s['interventions']:>4d}  [{flag}]")
        sol.to_excel(args.template, results / f"solution_{name}.xlsx")
    (results / "variant_summaries.json").write_text(json.dumps(summaries, indent=2))

    if not args.validate:
        print("\nConstructed variants written to", results)
        print("Re-run with --validate to simulate and pick the TOPSIS winner.")
        return

    print("[3/4] Full-year SWMM validation (parallel, this is slow)")
    from nbscombat.combat_validate import validate_solutions
    base_rpt = Path(args.baseline_rpt)
    if base_rpt.exists():
        baseline = parse_rpt(base_rpt.read_text(), cost=0.0, biodiversity=0.0)
        print(f"      baseline KPIs read from {base_rpt.name}")
    else:
        res = validate_solutions(args.inp, {"baseline": Solution()},
                                 results / "runs", n_parallel=1)
        baseline = res["baseline"]
    kpis = validate_solutions(args.inp, solutions, results / "runs",
                              n_parallel=args.parallel)
    for name, k in kpis.items():
        if isinstance(k, str):
            print(f"      {name}: {k}")

    print("[4/4] Ranking by TOPSIS and writing recommendation")
    indicators = {n: combat_report.indicators_from_kpis(k, baseline)
                  for n, k in kpis.items() if not isinstance(k, str)}
    ranking = combat_report.rank_variants(indicators)
    recommended = ranking[0][0]
    combat_report.write_report(results / "combat_report.md", baseline=baseline,
                               variant_kpis=kpis, indicators=indicators,
                               ranking=ranking, recommended=recommended,
                               summaries=summaries)
    # Promote the recommended variant to the official submission file.
    solutions[recommended].to_excel(args.template, results / "solution_SUBMIT.xlsx")

    print(f"\n=== TOPSIS ranking ===")
    for name, score in ranking:
        print(f"  {name:11s} {score:.3f}")
    print(f"\nRecommended submission: {recommended}  ->  "
          f"{results/'solution_SUBMIT.xlsx'}")
    print(f"Report: {results/'combat_report.md'}")


if __name__ == "__main__":
    main()
