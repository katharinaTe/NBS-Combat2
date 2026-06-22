"""SWMM model wrapper: decode a decision vector into LID placements, run the
SWMM engine over a suite of design storms, and return hydraulic / cost /
co-benefit key performance indicators (KPIs).

The wrapper is deliberately model-agnostic: it parses whatever ``baseline.inp``
it is given, discovers the sub-catchments and their imperviousness, and builds a
decision space of (sub-catchment x NBS-type) area fractions.  Swap in the
official Combat ``.inp`` and everything downstream is unchanged.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from pyswmm import Nodes, Simulation

from .nbs_catalog import (CATALOG, COBENEFIT_WEIGHTS, DEFAULT_PALETTE,
                          lid_controls_section)

# Feasibility ceilings (fraction of available source area that may be converted).
_MAX_IMPERV_USE = 0.95
_MAX_PERV_USE = 0.90
_MAX_FROMIMP_SUM = 95.0   # can't treat more than ~100% of impervious runoff


@dataclass
class StormSpec:
    key: str            # SWMM timeseries suffix, e.g. "T10" -> TS_T10
    label: str
    weight: float       # weight in the aggregated hydraulic objective


# Default design-storm suite for *optimisation* (binding storms only).
DEFAULT_STORMS = [
    StormSpec("T10", "10-year", 0.6),
    StormSpec("T100", "100-year", 0.4),
]
# Full suite for final verification / reporting.
VERIFICATION_STORMS = [
    StormSpec("T1", "1-year", 0.0),
    StormSpec("T10", "10-year", 0.6),
    StormSpec("T100", "100-year", 0.4),
]


@dataclass
class KPIs:
    flood_weighted: float            # weighted node-flooding volume (m3)
    flood_by_storm: Dict[str, float]
    peak_outflow: float              # max outfall peak flow across storms (m3/s)
    total_runoff: float              # summed surface runoff across storms (m3)
    cost: float                      # lifecycle cost (EUR)
    cobenefit: float                 # aggregated co-benefit index
    footprint: float                 # total NBS footprint (m2)


class SWMMModel:
    def __init__(self, inp_path: str | Path,
                 palette: List[str] = None,
                 storms: List[StormSpec] = None,
                 cobenefit_weights: Dict[str, float] = None,
                 sim_window_hours: float = 4.0):
        self.inp_path = Path(inp_path)
        self.base_text = self.inp_path.read_text()
        self.palette = palette or list(DEFAULT_PALETTE)
        self.storms = storms or list(DEFAULT_STORMS)
        self.cobenefit_weights = cobenefit_weights or dict(COBENEFIT_WEIGHTS)

        self.subcatchments = self._parse_subcatchments()
        # Decision variables: one (sub-catchment, NBS-type) pair per entry.
        self.var_index: List[Tuple[str, str]] = [
            (sc, t) for sc in self.subcatchments for t in self.palette
        ]
        self.n_var = len(self.var_index)
        self._lid_controls = lid_controls_section(self.palette)
        self._tmp = Path(tempfile.mkdtemp(prefix="nbscombat_"))

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def _parse_subcatchments(self) -> Dict[str, Dict[str, float]]:
        """Return {name: {area_m2, imperv_frac}} from the [SUBCATCHMENTS] block."""
        out: Dict[str, Dict[str, float]] = {}
        in_sec = False
        for line in self.base_text.splitlines():
            s = line.strip()
            if s.startswith("["):
                in_sec = s.upper().startswith("[SUBCATCHMENTS")
                continue
            if not in_sec or not s or s.startswith(";"):
                continue
            parts = s.split()
            # Name RainGage Outlet Area %Imperv Width %Slope ...
            name, _rg, _out, area_ha, imperv = parts[:5]
            out[name] = {
                "area_m2": float(area_ha) * 10000.0,
                "imperv_frac": float(imperv) / 100.0,
            }
        if not out:
            raise ValueError("No sub-catchments found in baseline model.")
        return out

    # ------------------------------------------------------------------ #
    # Decode a decision vector into physical LID placements
    # ------------------------------------------------------------------ #
    def decode(self, x) -> Dict[Tuple[str, str], float]:
        """Map x in [0,1]^n_var to feasible LID footprints (m2) per (sc, type)."""
        # Desired footprint per variable, capped by per-type suitability.
        desired: Dict[Tuple[str, str], float] = {}
        for v, (sc, t) in enumerate(self.var_index):
            nbs = CATALOG[t]
            sca = self.subcatchments[sc]
            src = (sca["area_m2"] * sca["imperv_frac"] if nbs.surface == "impervious"
                   else sca["area_m2"] * (1.0 - sca["imperv_frac"]))
            desired[(sc, t)] = max(0.0, float(x[v])) * nbs.max_area_fraction * src

        # Per sub-catchment, enforce land-availability on impervious & pervious
        # groups separately by proportional scaling.
        for sc, sca in self.subcatchments.items():
            imp_cap = _MAX_IMPERV_USE * sca["area_m2"] * sca["imperv_frac"]
            perv_cap = _MAX_PERV_USE * sca["area_m2"] * (1.0 - sca["imperv_frac"])
            imp_sum = sum(desired[(sc, t)] for t in self.palette
                          if CATALOG[t].surface == "impervious")
            perv_sum = sum(desired[(sc, t)] for t in self.palette
                           if CATALOG[t].surface == "pervious")
            if imp_sum > imp_cap and imp_sum > 0:
                f = imp_cap / imp_sum
                for t in self.palette:
                    if CATALOG[t].surface == "impervious":
                        desired[(sc, t)] *= f
            if perv_sum > perv_cap and perv_sum > 0:
                f = perv_cap / perv_sum
                for t in self.palette:
                    if CATALOG[t].surface == "pervious":
                        desired[(sc, t)] *= f
        # Drop negligible placements.
        return {k: a for k, a in desired.items() if a >= 1.0}

    def _usage_section(self, placements: Dict[Tuple[str, str], float]) -> str:
        lines = ["[LID_USAGE]",
                 ";;Subcat  LIDProcess  Number  Area  Width  InitSat  FromImp  ToPerv"]
        # Group by sub-catchment to normalise treated-impervious fractions.
        by_sc: Dict[str, List[Tuple[str, float]]] = {}
        for (sc, t), area in placements.items():
            by_sc.setdefault(sc, []).append((t, area))
        for sc, items in by_sc.items():
            fromimp = {t: CATALOG[t].capture_per_m2 * area for t, area in items}
            tot = sum(fromimp.values())
            if tot > _MAX_FROMIMP_SUM:
                f = _MAX_FROMIMP_SUM / tot
                fromimp = {t: v * f for t, v in fromimp.items()}
            for t, area in items:
                nbs = CATALOG[t]
                lines.append(
                    f"{sc:6s}  {nbs.swmm_process:10s}  1  {area:9.1f}  0  0  "
                    f"{fromimp[t]:6.2f}  {nbs.to_pervious}")
        return "\n".join(lines)

    def render_inp(self, placements, storm_key: str) -> str:
        text = self.base_text
        if placements:
            block = self._lid_controls + "\n\n" + self._usage_section(placements)
            text = text.replace("[REPORT]", block + "\n\n[REPORT]", 1)
        text = re.sub(r"TIMESERIES TS_\w+", f"TIMESERIES TS_{storm_key}", text)
        return text

    # ------------------------------------------------------------------ #
    # Simulation
    # ------------------------------------------------------------------ #
    def _run_storm(self, placements, storm: StormSpec):
        inp = self.render_inp(placements, storm.key)
        p = self._tmp / f"run_{storm.key}.inp"
        p.write_text(inp)
        flood = 0.0
        runoff = 0.0
        peak = 0.0
        with Simulation(str(p)) as sim:
            node_list = list(Nodes(sim))   # materialise once; iterator is single-use
            outfalls = [n for n in node_list if n.is_outfall()]
            for _ in sim:
                for o in outfalls:
                    peak = max(peak, o.total_inflow)
            for n in node_list:
                flood += n.statistics.get("flooding_volume", 0.0)
        return flood, runoff, peak

    def evaluate(self, x) -> KPIs:
        placements = self.decode(x)
        flood_by_storm: Dict[str, float] = {}
        weighted = 0.0
        peak = 0.0
        runoff = 0.0
        for storm in self.storms:
            f, r, pk = self._run_storm(placements, storm)
            flood_by_storm[storm.key] = f
            weighted += storm.weight * f
            peak = max(peak, pk)
            runoff += r
        cost = sum(area * CATALOG[t].lifecycle_cost_m2()
                   for (sc, t), area in placements.items())
        cobenefit = sum(area * CATALOG[t].cobenefit_score_m2(self.cobenefit_weights)
                        for (sc, t), area in placements.items())
        footprint = sum(placements.values())
        return KPIs(flood_weighted=weighted, flood_by_storm=flood_by_storm,
                    peak_outflow=peak, total_runoff=runoff, cost=cost,
                    cobenefit=cobenefit, footprint=footprint)

    # ------------------------------------------------------------------ #
    def placement_table(self, x) -> List[dict]:
        """Human-readable breakdown of a design's LID placements."""
        placements = self.decode(x)
        rows = []
        for (sc, t), area in sorted(placements.items()):
            nbs = CATALOG[t]
            rows.append({
                "subcatchment": sc,
                "nbs": nbs.name,
                "type": t,
                "area_m2": round(area, 1),
                "capital_eur": round(area * nbs.capital_eur_m2, 0),
                "lifecycle_eur": round(area * nbs.lifecycle_cost_m2(), 0),
            })
        return rows
