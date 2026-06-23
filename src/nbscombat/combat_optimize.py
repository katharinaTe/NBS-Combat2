"""Static cost-effectiveness optimiser for the NBS Combat.

The official case study runs a full year of 5-second dynamic-wave routing over
805 sub-catchments -- >10 minutes per simulation -- so a metaheuristic with
thousands of SWMM evaluations is infeasible. Instead we exploit the (near)
separable structure of the problem: each LID mainly disconnects impervious
runoff from its own sub-catchment, so a budgeted greedy on a transparent
retained-runoff-per-euro score builds a strong, rule-compliant solution with
**zero** simulations. SWMM is then used only to *validate* a handful of strategy
variants on the full year.

Capture model
-------------
An LID of footprint ``A`` treating impervious area ``T`` (= FromImp% x
sub-catchment impervious area) retains, over the year, roughly::

    capture = min( T * R ,  A * K_type )

where ``R`` is the annual impervious-runoff depth (m/yr) and ``K_type`` the
annual effective retention depth the LID can process per m² (storage cycling +
infiltration + evapotranspiration, inferred from the .inp LID parameters). This
min() captures the diminishing return of oversizing an LID relative to its load
and yields an *optimal footprint* ``A* = T*R / K_type`` (capped at the allowed
maximum), so continuous-area LIDs are auto-sized to their treated load rather
than blindly maximised.

Decision rules honoured (see combat_data): one green + one roof + one road LID
per sub-catchment; one type per group; roof LIDs full-area-or-zero; %impervious
set to the allowed maximum; total cost < EUR 650,000. The biodiversity indicator
-- min over {bio-retention, dry swale, extensive & intensive green roof} of
summed area -- is raised by a cheapest-first seeding phase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .combat_data import (BIODIVERSITY_TYPES, BUDGET_EUR, NBS_TYPES,
                          SubcatchmentLimits)
from .combat_model import Placement, Solution

# Annual impervious-runoff depth (m/yr): 0.783 m rain x runoff coefficient.
ANNUAL_RUNOFF_DEPTH = 0.783 * 0.9

# Annual effective retention depth per m² of LID footprint (m/yr), inferred from
# each LID's storage / soil / infiltration design in the provided .inp.
RETENTION_K = {
    "soakaway": 40.0,        # 2.5 m berm + 0.5 m store, 360 mm/h soil, 36 seepage
    "bioretention": 8.0,     # 0.3 m soil + 0.5 m store, 30 mm/h, 7 seepage
    "dryswale": 4.0,         # 0.3 m soil, 7 mm/h
    "permeable": 12.0,       # 0.1 m soil + 0.1 m store, 360 mm/h
    "ext_green_roof": 0.6,   # 0.1 m substrate, ET-dominated, roof only
    "int_green_roof": 1.2,   # 0.25 m substrate
    "cistern": 8.0,          # 1 m store, drained/reused between events
}
MIN_AREA = 1.0               # m² floor so base cost is not amortised over ~0


@dataclass
class Candidate:
    subcatch: str
    nbs_key: str
    group: str
    max_area: float
    from_imp_pct: float
    treated_imp_m2: float           # T
    binary: bool

    def runoff_load(self) -> float:
        return self.treated_imp_m2 * ANNUAL_RUNOFF_DEPTH      # m³/yr

    def auto_area(self) -> float:
        """Footprint sized to the treated load (capped at the allowed max)."""
        if self.binary:
            return self.max_area
        k = RETENTION_K[self.nbs_key]
        a_star = self.runoff_load() / k if k > 0 else self.max_area
        return max(MIN_AREA, min(self.max_area, a_star))

    def cost(self, area: float) -> float:
        return NBS_TYPES[self.nbs_key].element_cost(area)

    def capture(self, area: float) -> float:
        k = RETENTION_K[self.nbs_key]
        return min(self.runoff_load(), area * k)

    def ce(self, area: Optional[float] = None) -> float:
        a = self.auto_area() if area is None else area
        c = self.cost(a)
        return self.capture(a) / c if c > 0 else 0.0


def build_candidates(limits: Dict[str, SubcatchmentLimits],
                     geom: Dict[str, Dict[str, float]]) -> List[Candidate]:
    cands: List[Candidate] = []
    for sc, lim in limits.items():
        imp_m2 = geom.get(sc, {}).get("imperv_m2", 0.0)
        for key, t in NBS_TYPES.items():
            max_area = lim.max_area.get(key, 0.0)
            from_imp = lim.max_imperv_pct.get(key, 0.0)
            if max_area <= 0 or from_imp <= 0:
                continue
            treated = (from_imp / 100.0) * imp_m2
            cands.append(Candidate(sc, key, t.group, max_area, from_imp,
                                   treated, t.binary_area))
    return cands


def greedy_solution(limits, geom, *, budget: float = BUDGET_EUR,
                    budget_use: float = 0.985,
                    bio_target: float = 0.0) -> Solution:
    """Two-phase budgeted greedy.

    Phase A seeds each biodiversity type to ``bio_target`` m² (cheapest per m²
    first; continuous types are part-sized to hit the target exactly, roof types
    installed full-area). Phase B fills the remaining budget by
    retained-runoff-per-euro. Sweep ``bio_target`` to trace the biodiversity vs
    capture trade-off.
    """
    cap = budget * budget_use
    cands = build_candidates(limits, geom)

    sol = Solution()
    state = {"spent": 0.0}
    used_group: Dict[str, set] = {}
    used_pair: set = set()
    bio_area = {k: 0.0 for k in BIODIVERSITY_TYPES}

    def install(c: Candidate, area: float) -> bool:
        if area < MIN_AREA or c.cost(area) + state["spent"] > cap:
            return False
        if c.group in used_group.get(c.subcatch, set()):
            return False
        if (c.subcatch, c.nbs_key) in used_pair:
            return False
        sol.add(c.subcatch, c.nbs_key, area, c.from_imp_pct)
        state["spent"] += c.cost(area)
        used_group.setdefault(c.subcatch, set()).add(c.group)
        used_pair.add((c.subcatch, c.nbs_key))
        if c.nbs_key in bio_area:
            bio_area[c.nbs_key] += area
        return True

    # ---- Phase A: biodiversity seeding ----------------------------------- #
    if bio_target > 0:
        for k in BIODIVERSITY_TYPES:
            binary = NBS_TYPES[k].binary_area
            pool = sorted((c for c in cands if c.nbs_key == k),
                          key=lambda c: c.cost(c.max_area) / c.max_area)
            for c in pool:
                if bio_area[k] >= bio_target:
                    break
                if binary:
                    install(c, c.max_area)
                else:
                    need = bio_target - bio_area[k]
                    install(c, min(c.max_area, need))

    # ---- Phase B: capture fill ------------------------------------------- #
    pool = sorted(cands, key=lambda c: c.ce(), reverse=True)
    for c in pool:
        install(c, c.auto_area())

    # Ensure summed %-impervious treated per sub-catchment stays <=100% (SWMM
    # ERROR 188): roof+road keep their surface fractions, green takes the rest.
    sol.apportion_from_imp()
    return sol


def competition_solution(limits, geom, *, budget: float = BUDGET_EUR,
                         budget_use: float = 0.99, bio_target: float = 1270.0,
                         green_cap: float = 40.0) -> Solution:
    """Maximise biodiversity (all four green types to ``bio_target``) co-located
    with capture, then fill the rest of the budget with the most
    capture-efficient pavement/cistern fillers.

    Each biodiversity type is placed sequentially over the highest-impervious
    sub-catchments. Green-area cells (bio-retention, dry swale) are capped at
    ``green_cap`` m² per install so the budget spreads across many high-runoff
    sub-catchments (broad CSO/TSS capture) rather than a few oversized cells;
    roof LIDs take their full allowed area.
    """
    cap = budget * budget_use
    cands = {(c.subcatch, c.nbs_key): c for c in build_candidates(limits, geom)}
    subs = sorted(geom, key=lambda s: geom[s].get("imperv_m2", 0.0), reverse=True)

    sol = Solution()
    state = {"spent": 0.0}
    used_group: Dict[str, set] = {}

    def place(sc, key, area):
        c = cands.get((sc, key))
        if c is None or area < MIN_AREA:
            return 0.0
        if c.group in used_group.get(sc, set()):
            return 0.0
        if c.cost(area) + state["spent"] > cap:
            return 0.0
        sol.add(sc, key, area, c.from_imp_pct)
        state["spent"] += c.cost(area)
        used_group.setdefault(sc, set()).add(c.group)
        return area

    # 1-4. biodiversity types, highest-impervious first.
    for key in ("bioretention", "dryswale", "ext_green_roof", "int_green_roof"):
        binary = NBS_TYPES[key].binary_area
        total = 0.0
        for sc in subs:
            if total >= bio_target:
                break
            c = cands.get((sc, key))
            if c is None:
                continue
            area = c.max_area if binary else min(c.max_area, green_cap,
                                                 bio_target - total)
            total += place(sc, key, area)

    # 5-6. capture fill with the most cost-effective pavement / cisterns.
    fillers = sorted((c for c in cands.values()
                      if c.nbs_key in ("permeable", "cistern")),
                     key=lambda c: c.ce(), reverse=True)
    for c in fillers:
        place(c.subcatch, c.nbs_key, c.auto_area())

    sol.apportion_from_imp()
    return sol


def winning_solution(limits, geom, *, budget: float = BUDGET_EUR,
                     budget_use: float = 0.99, bio_target: float = 1300.0,
                     fill_frac: float = 0.12, green_area_cap: float = 25.0) -> Solution:
    """Biodiversity-and-capture co-maximising greedy (competition strategy).

    The biodiversity indicator rewards *total* green area, and bio-retention /
    dry swale treat 100% of a sub-catchment's impervious area, so the same green
    LIDs that lift biodiversity also drive flood/CSO/TSS reduction. Three passes:

    1. *Spread* -- walk sub-catchments from most to least impervious; give each
       green slot to the lagging of {bio-retention, dry swale} and each roof slot
       to the lagging of {extensive, intensive green roof}, auto-sized to the
       treated load. This maximises capture coverage and keeps the four types
       balanced.
    2. *Enlarge for biodiversity* -- while a biodiversity type's total area is
       below ``bio_target``, grow its existing installs (highest-impervious
       first) toward their allowed maximum. Enlarging costs only unit price (no
       new base cost), so it is the budget-efficient way to lift biodiversity;
       accepting the diminishing capture return of larger cells.
    3. *Capture fill* -- spend a remaining slice (``fill_frac`` of budget) on the
       best capture-per-euro fillers (permeable pavement, cisterns).
    """
    cap = budget * budget_use
    cands = {(c.subcatch, c.nbs_key): c for c in build_candidates(limits, geom)}

    sol = Solution()
    state = {"spent": 0.0}
    used_group: Dict[str, set] = {}
    bio_area = {k: 0.0 for k in BIODIVERSITY_TYPES}
    placed: Dict[tuple, Placement] = {}

    def install(c: Candidate, area: float, limit: float):
        if area < MIN_AREA or c.cost(area) + state["spent"] > limit:
            return False
        if c.group in used_group.get(c.subcatch, set()):
            return False
        sol.add(c.subcatch, c.nbs_key, area, c.from_imp_pct)
        state["spent"] += c.cost(area)
        used_group.setdefault(c.subcatch, set()).add(c.group)
        placed[(c.subcatch, c.nbs_key)] = sol.placements[c.subcatch][c.group]
        if c.nbs_key in bio_area:
            bio_area[c.nbs_key] += area
        return True

    subs = sorted(geom, key=lambda s: geom[s].get("imperv_m2", 0.0), reverse=True)
    spread_budget = cap * (1.0 - fill_frac)

    # ---- Pass 1: green-area biodiversity, co-located with capture ---------- #
    # Interleave bio-retention / dry swale across the highest-impervious
    # sub-catchments (both treat 100% impervious -> capture) sizing each to take
    # its sub-catchment's allowed area until each type reaches bio_target.
    green_pair = ["bioretention", "dryswale"]
    gi = 0
    for sc in subs:
        if all(bio_area[k] >= bio_target for k in green_pair):
            break
        # try the lagging green type first in this sub-catchment
        for key in sorted(green_pair, key=lambda k: bio_area[k]):
            if bio_area[key] >= bio_target:
                continue
            c = cands.get((sc, key))
            if c is None:
                continue
            area = min(c.max_area, bio_target - bio_area[key])
            if install(c, area, spread_budget):
                break

    # ---- Pass 2: roof biodiversity (extensive / intensive green roof) ------ #
    roof_pair = ["ext_green_roof", "int_green_roof"]
    for sc in subs:
        if all(bio_area[k] >= bio_target for k in roof_pair):
            break
        for key in sorted(roof_pair, key=lambda k: bio_area[k]):
            if bio_area[key] >= bio_target:
                continue
            c = cands.get((sc, key))
            if c and install(c, c.max_area, spread_budget):
                break

    # ---- Pass 3: capture fill (permeable, cisterns) ----------------------- #
    fillers = sorted((c for c in cands.values()
                      if c.nbs_key in ("permeable", "cistern")),
                     key=lambda c: c.ce(), reverse=True)
    for c in fillers:
        install(c, c.auto_area(), cap)

    sol.apportion_from_imp()
    return sol


def summarise(sol: Solution) -> dict:
    by_type = sol.area_by_type()
    return {
        "cost": round(sol.total_cost(), 0),
        "biodiversity": round(sol.biodiversity(), 2),
        "interventions": sol.n_interventions(),
        "subcatchments": len(sol.placements),
        "area_by_type": {k: round(v, 1) for k, v in by_type.items() if v > 0},
    }
