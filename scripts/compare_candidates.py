#!/usr/bin/env python
"""Generate competition candidates and validate them on a chosen SWMM model.

Usage:
    python scripts/compare_candidates.py --inp data/official_event/Case_study_event.inp
    python scripts/compare_candidates.py --inp data/official/Case_study.inp   # full year
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nbscombat.combat_data import load_limits, parse_subcatchment_geometry
from nbscombat.combat_model import Solution
from nbscombat.combat_optimize import competition_solution, summarise
from nbscombat.combat_validate import validate_solutions

OFFICIAL_INP = ROOT / "data/official/Case_study.inp"
IMPL = ROOT / "data/official/implementation_details.xlsx"
TEMPLATE = ROOT / "data/official/solutions_template.xlsx"

# Candidate set spanning the biodiversity <-> capture trade-off.
CANDIDATES = {
    "biodiv1270": dict(bio_target=1270, green_cap=40),
    "biodiv1100": dict(bio_target=1100, green_cap=40),
    "biodiv1000": dict(bio_target=1000, green_cap=55),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default=str(ROOT / "data/official_event/Case_study_event.inp"))
    ap.add_argument("--tag", default="event")
    args = ap.parse_args()

    limits = load_limits(IMPL)
    geom = parse_subcatchment_geometry(OFFICIAL_INP)

    sols = {"baseline": Solution()}
    for name, kw in CANDIDATES.items():
        sol = competition_solution(limits, geom, **kw)
        sols[name] = sol
        s = summarise(sol)
        print(f"{name:11s} cost €{s['cost']:>7,.0f} biodiv {s['biodiversity']:>6.0f} "
              f"ivt {s['interventions']:>4d}  valid={not sol.validate(limits)}", flush=True)
        sol.to_excel(str(TEMPLATE), str(ROOT / f"results_combat/solution_{name}.xlsx"))

    print(f"\nValidating on {Path(args.inp).name} ...", flush=True)
    t = time.time()
    kpis = validate_solutions(args.inp, sols, ROOT / f"results_combat/runs_{args.tag}",
                              n_parallel=4)
    print(f"done in {time.time()-t:.0f}s", flush=True)

    base = kpis["baseline"]
    rows = {}
    print(f"\n{'cand':11s} {'flood↓':>8s} {'evap↑':>7s} {'wwtp↑':>7s} {'cso↓':>7s} {'tss↓':>9s}")
    for name, k in kpis.items():
        if isinstance(k, str):
            print(f"{name}: {k}"); continue
        if name == "baseline":
            print(f"{'baseline':11s} flood={k.flood_volume:.4f} evap={k.evaporation:.3f} "
                  f"wwtp={k.wwtp_volume:.3f} cso={k.cso_volume:.3f} tss={k.cso_tss:.1f}")
            continue
        d = dict(flood=base.flood_volume - k.flood_volume,
                 evap=k.evaporation - base.evaporation,
                 wwtp=k.wwtp_volume - base.wwtp_volume,
                 cso=base.cso_volume - k.cso_volume,
                 tss=base.cso_tss - k.cso_tss,
                 cost=sols[name].total_cost(), biodiv=sols[name].biodiversity())
        rows[name] = d
        print(f"{name:11s} {d['flood']:>8.4f} {d['evap']:>7.3f} {d['wwtp']:>7.3f} "
              f"{d['cso']:>7.3f} {d['tss']:>9.1f}")
    out = ROOT / f"results_combat/candidates_{args.tag}.json"
    out.write_text(json.dumps({"baseline": {k: getattr(base, k) for k in
                   ("flood_volume","evaporation","wwtp_volume","cso_volume","cso_tss")},
                   "deltas": rows}, indent=2, default=float))
    Path(f"/tmp/compare_{args.tag}_done.txt").write_text("DONE\n")
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
