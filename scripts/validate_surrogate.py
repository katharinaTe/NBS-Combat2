#!/usr/bin/env python
"""Validate and rank Combat variants on a storm-rich surrogate window.

The official full-year model is too slow to run repeatedly (dynamic-wave
timestep collapse -> >1 h per run), so variants are compared on a shorter,
storm-rich window (default: August 2018, the wettest month, with a warm-up).
This gives a faithful *relative* ranking of the strategies and confirms the
direction of every benefit indicator. The organisers score the chosen
submission on the full year; this step only selects which variant to submit.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat.combat_data import load_limits, parse_subcatchment_geometry
from nbscombat.combat_model import Solution
from nbscombat.combat_optimize import greedy_solution, summarise
from nbscombat.combat_validate import validate_solutions
from nbscombat import combat_report

OFFICIAL_INP = ROOT / "data/official/Case_study.inp"
SURROGATE_INP = ROOT / "data/official/Case_study_aug.inp"
IMPL = ROOT / "data/official/implementation_details.xlsx"
TEMPLATE = ROOT / "data/official/solutions_template.xlsx"
RESULTS = ROOT / "results_combat"

VARIANTS = {
    "capture":    dict(bio_target=0),
    "balanced":   dict(bio_target=300),
    "biodiverse": dict(bio_target=600),
    "thrifty":    dict(bio_target=300, budget=450_000.0),
}


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    limits = load_limits(IMPL)
    geom = parse_subcatchment_geometry(OFFICIAL_INP)

    solutions = {"baseline": Solution()}
    summaries = {}
    for name, kw in VARIANTS.items():
        sol = greedy_solution(limits, geom, **kw)
        solutions[name] = sol
        summaries[name] = summarise(sol)
        sol.to_excel(str(TEMPLATE), str(RESULTS / f"solution_{name}.xlsx"))

    print(f"Validating {len(solutions)} designs on {SURROGATE_INP.name} ...",
          flush=True)
    t = time.time()
    kpis = validate_solutions(str(SURROGATE_INP), solutions,
                              RESULTS / "runs_aug", n_parallel=4)
    print(f"Validation finished in {time.time()-t:.0f}s", flush=True)

    for name, k in kpis.items():
        if isinstance(k, str):
            print(f"  {name}: {k}", flush=True)

    baseline = kpis["baseline"]
    indicators = {n: combat_report.indicators_from_kpis(k, baseline)
                  for n, k in kpis.items()
                  if n != "baseline" and not isinstance(k, str)}
    ranking = combat_report.rank_variants(indicators)
    recommended = ranking[0][0]

    combat_report.write_report(RESULTS / "combat_report.md", baseline=baseline,
                               variant_kpis=kpis, indicators=indicators,
                               ranking=ranking, recommended=recommended,
                               summaries=summaries)
    solutions[recommended].to_excel(str(TEMPLATE),
                                    str(RESULTS / "solution_SUBMIT.xlsx"))

    # Machine-readable dump.
    dump = {"window": "August 2018 (surrogate)", "recommended": recommended,
            "ranking": [(n, float(s)) for n, s in ranking],
            "baseline_kpis": {k: getattr(baseline, k) for k in
                              ("flood_volume", "evaporation", "wwtp_volume",
                               "cso_volume", "cso_tss")},
            "variant_indicators": {n: ind.__dict__ for n, ind in indicators.items()},
            "summaries": summaries}
    (RESULTS / "validation_aug.json").write_text(json.dumps(dump, indent=2, default=float))

    print("\n=== TOPSIS ranking (August surrogate) ===", flush=True)
    for name, score in ranking:
        print(f"  {name:11s} {score:.3f}", flush=True)
    print(f"Recommended: {recommended} -> results_combat/solution_SUBMIT.xlsx",
          flush=True)
    Path("/tmp/validate_done.txt").write_text(f"DONE {recommended}\n")


if __name__ == "__main__":
    main()
