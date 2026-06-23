"""Official UDM-2025 NBS Combat: solution representation, SWMM evaluation, and
Excel I/O.

A :class:`Solution` is the per-sub-catchment choice of (green, roof, road) NBS
and their areas. It can be:

* rendered into the SWMM ``[LID_USAGE]`` section and simulated for the full year,
* scored on the seven Combat indicators read from the SWMM ``.rpt`` file,
* exported to / imported from the official ``solutions.xlsx`` template.
"""
from __future__ import annotations

import math
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import openpyxl
from pyswmm import Simulation

from .combat_data import (BIODIVERSITY_TYPES, BUDGET_EUR, EXCEL_COLUMN_ORDER,
                          GROUP_TYPES, NBS_TYPES, SubcatchmentLimits)


@dataclass
class Placement:
    """One NBS installed in one sub-catchment."""
    nbs_key: str
    area: float          # m2
    from_imp_pct: float  # % impervious area treated


@dataclass
class Solution:
    # subcatchment -> {group -> Placement}
    placements: Dict[str, Dict[str, Placement]] = field(default_factory=dict)

    def add(self, subcatch: str, nbs_key: str, area: float, from_imp_pct: float):
        if area <= 0:
            return
        group = NBS_TYPES[nbs_key].group
        self.placements.setdefault(subcatch, {})[group] = Placement(
            nbs_key=nbs_key, area=area, from_imp_pct=from_imp_pct)

    # ------------------------------------------------------------------ #
    # Indicators that do not need a simulation
    # ------------------------------------------------------------------ #
    def total_cost(self) -> float:
        c = 0.0
        for groups in self.placements.values():
            for p in groups.values():
                c += NBS_TYPES[p.nbs_key].element_cost(p.area)
        return c

    def biodiversity(self) -> float:
        """min over {bioretention, dry swale, ext GR, int GR} of summed area."""
        totals = {k: 0.0 for k in BIODIVERSITY_TYPES}
        for groups in self.placements.values():
            for p in groups.values():
                if p.nbs_key in totals:
                    totals[p.nbs_key] += p.area
        return min(totals.values())

    def area_by_type(self) -> Dict[str, float]:
        out: Dict[str, float] = {k: 0.0 for k in NBS_TYPES}
        for groups in self.placements.values():
            for p in groups.values():
                out[p.nbs_key] += p.area
        return out

    def n_interventions(self) -> int:
        return sum(len(g) for g in self.placements.values())

    # ------------------------------------------------------------------ #
    # Validation against the Combat rules
    # ------------------------------------------------------------------ #
    def validate(self, limits: Dict[str, SubcatchmentLimits]) -> list[str]:
        errs = []
        for sc, groups in self.placements.items():
            lim = limits.get(sc)
            if lim is None:
                errs.append(f"{sc}: unknown sub-catchment")
                continue
            for group, p in groups.items():
                t = NBS_TYPES[p.nbs_key]
                if t.group != group:
                    errs.append(f"{sc}: {p.nbs_key} wrong group")
                maxa = lim.max_area.get(p.nbs_key, 0.0)
                if p.area > maxa + 1e-6:
                    errs.append(f"{sc}/{p.nbs_key}: area {p.area:.2f} > max {maxa:.2f}")
                if t.binary_area and abs(p.area - maxa) > 1e-6 and p.area > 0:
                    errs.append(f"{sc}/{p.nbs_key}: roof LID must be full area ({maxa}) or 0")
                maxp = lim.max_imperv_pct.get(p.nbs_key, 0.0)
                if p.from_imp_pct > maxp + 1e-6:
                    errs.append(f"{sc}/{p.nbs_key}: %imp {p.from_imp_pct} > max {maxp}")
        cost = self.total_cost()
        if cost >= BUDGET_EUR:
            errs.append(f"budget violated: {cost:,.0f} >= {BUDGET_EUR:,.0f}")
        return errs

    def apportion_from_imp(self, margin: float = 0.5):
        """Cap the summed % impervious treated per sub-catchment to <=100%.

        SWMM rejects a sub-catchment whose LIDs collectively capture more than
        its impervious area (ERROR 188). Roof and road LIDs treat their own
        (disjoint) surface fractions; the green LID treats the remaining
        impervious. A small ``margin`` keeps the sum strictly below 100%.
        """
        for groups in self.placements.values():
            total = 100.0 - margin
            used = 0.0
            for grp in ("road", "roof"):
                p = groups.get(grp)
                if p:
                    p.from_imp_pct = min(p.from_imp_pct, max(0.0, total - used))
                    used += p.from_imp_pct
            green = groups.get("green")
            if green:
                green.from_imp_pct = max(0.0, min(green.from_imp_pct, total - used))

    # ------------------------------------------------------------------ #
    # SWMM rendering
    # ------------------------------------------------------------------ #
    def lid_usage_lines(self) -> str:
        lines = []
        for sc, groups in self.placements.items():
            for p in groups.values():
                proc = NBS_TYPES[p.nbs_key].swmm_name
                width = round(math.sqrt(p.area), 4)
                # Subcatch LID Number Area Width InitSat FromImp ToPerv
                lines.append(
                    f"{sc:16s} {proc:20s} 1  {p.area:10.4f} {width:10.4f} 0  "
                    f"{p.from_imp_pct:8.4f} 0")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Excel I/O (official template)
    # ------------------------------------------------------------------ #
    def to_excel(self, template_path: str | Path, out_path: str | Path):
        wb = openpyxl.load_workbook(template_path)
        ws_area = wb["LID_Areas"]
        ws_pct = wb["LID_Percentage_Implemented"]

        def trunc(x, n=4):
            # Floor to n decimals so a written value never exceeds the allowed
            # maximum it was clamped to (round() can push it just over).
            f = 10 ** n
            return math.floor(x * f) / f

        # Map subcatchment -> row.
        row_of = {}
        for r in range(3, ws_area.max_row + 1):
            name = ws_area.cell(r, 1).value
            if name is not None:
                row_of[str(name)] = r
        # Fill every cell (0 where nothing implemented).
        for sc, r in row_of.items():
            groups = self.placements.get(sc, {})
            chosen = {p.nbs_key: p for p in groups.values()}
            for j, key in enumerate(EXCEL_COLUMN_ORDER):
                col = 2 + j
                p = chosen.get(key)
                ws_area.cell(r, col).value = trunc(p.area) if p else 0
                ws_pct.cell(r, col).value = trunc(p.from_imp_pct) if p else 0
        wb.save(out_path)

    @classmethod
    def from_excel(cls, path: str | Path) -> "Solution":
        wb = openpyxl.load_workbook(path, data_only=True)
        ws_area = wb["LID_Areas"]
        ws_pct = wb["LID_Percentage_Implemented"]
        sol = cls()
        for r in range(3, ws_area.max_row + 1):
            name = ws_area.cell(r, 1).value
            if name is None:
                continue
            for j, key in enumerate(EXCEL_COLUMN_ORDER):
                area = ws_area.cell(r, 2 + j).value or 0
                pct = ws_pct.cell(r, 2 + j).value or 0
                if area and area > 0:
                    sol.add(str(name), key, float(area), float(pct))
        return sol


# --------------------------------------------------------------------------- #
# SWMM evaluation
# --------------------------------------------------------------------------- #
@dataclass
class CombatKPIs:
    cost: float
    biodiversity: float
    flood_volume: float          # VF (10^6 L)  -- lower better
    evaporation: float           # E  (mm or 10^6 L) -- higher better
    wwtp_volume: float           # V_WWTP (10^6 L) -- higher better
    cso_volume: float            # V_CSO (10^6 L) -- lower better
    cso_tss: float               # M_TSS (kg) -- lower better
    raw: dict = field(default_factory=dict)


class CombatEvaluator:
    """Runs the official case study with a given solution and extracts KPIs."""

    def __init__(self, base_inp: str | Path, workdir: str | Path | None = None):
        self.base_inp = Path(base_inp)
        self.base_dir = self.base_inp.parent
        self.base_text = self.base_inp.read_text()
        self.workdir = Path(workdir) if workdir else Path(
            tempfile.mkdtemp(prefix="combat_"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        # Symlink (or copy) the rain/temp data into the workdir so relative
        # SWMM file references resolve.
        for dat in ("rain2018.dat", "temp2018.dat"):
            src = self.base_dir / dat
            dst = self.workdir / dat
            if src.exists() and not dst.exists():
                try:
                    dst.symlink_to(src.resolve())
                except OSError:
                    shutil.copy(src, dst)

    def write_inp(self, sol: Solution, name: str = "run") -> Path:
        # Build LID_USAGE block then write a complete .inp into the workdir.
        block = ("[LID_USAGE]\n"
                 ";;Subcatchment   LID Process      Number  Area       Width"
                 "      InitSat    FromImp    ToPerv\n")
        block += sol.lid_usage_lines() + "\n"
        text = re.sub(r"\[LID_USAGE\][^\[]*", block + "\n", self.base_text, count=1)
        p = self.workdir / f"{name}.inp"
        p.write_text(text)
        return p

    def simulate(self, sol: Solution, name: str = "run") -> CombatKPIs:
        inp = self.write_inp(sol, name)
        rpt = inp.with_suffix(".rpt")
        with Simulation(str(inp)) as sim:
            for _ in sim:
                pass
        return parse_rpt(rpt.read_text(), cost=sol.total_cost(),
                         biodiversity=sol.biodiversity())


# --------------------------------------------------------------------------- #
# .rpt parsing  (finalised against the real baseline report)
# --------------------------------------------------------------------------- #
def _continuity_value(text: str, section: str, label: str) -> float:
    """Return the 10^6-L volume column for a labelled continuity row."""
    si = text.find(section)
    if si < 0:
        return float("nan")
    chunk = text[si:si + 2000]
    m = re.search(rf"{re.escape(label)}\s*\.*\s+([-\d.]+)\s+([-\d.]+)", chunk)
    if not m:
        return float("nan")
    return float(m.group(1))


def parse_rpt(text: str, cost: float, biodiversity: float) -> CombatKPIs:
    flood = _continuity_value(text, "Flow Routing Continuity", "Flooding Loss")
    evap = _continuity_value(text, "Runoff Quantity Continuity", "Evaporation Loss")

    # Outfall Loading Summary: node rows with Total Volume (col) and Total TSS.
    wwtp_vol = cso_vol = cso_tss = float("nan")
    oi = text.find("Outfall Loading Summary")
    if oi >= 0:
        chunk = text[oi:oi + 3000]
        for line in chunk.splitlines():
            parts = line.split()
            if not parts:
                continue
            node = parts[0]
            if node == "WWTP" and len(parts) >= 6:
                wwtp_vol = float(parts[-2])
            elif node == "CSO_overflow" and len(parts) >= 6:
                cso_vol = float(parts[-2])
                cso_tss = float(parts[-1])
    return CombatKPIs(cost=cost, biodiversity=biodiversity, flood_volume=flood,
                      evaporation=evap, wwtp_volume=wwtp_vol, cso_volume=cso_vol,
                      cso_tss=cso_tss,
                      raw={"flood": flood, "evap": evap, "wwtp": wwtp_vol,
                           "cso": cso_vol, "tss": cso_tss})
