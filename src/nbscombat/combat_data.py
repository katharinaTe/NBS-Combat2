"""Official UDM-2025 NBS Combat: data model.

Loads the per-sub-catchment implementation constraints from
``implementation_details.xlsx`` and encodes the seven allowed NBS, their cost
structure (Table 8 of the Combat description), competition rules, and the
biodiversity accounting.

Combat rules encoded here
-------------------------
* Three NBS *groups* per sub-catchment may be combined in parallel:
  green (treats all impervious), roof (treats roof area), road (treats access
  road area).
* Within the green group at most ONE type (soakaway | bio-retention | dry swale)
  with a continuous area in [0, max].
* Within the roof group at most ONE type (extensive | intensive green roof |
  cistern); roof LIDs are BINARY -- either the full allowed roof area or 0.
* The road group is a single type (permeable pavement), continuous [0, max].
* Total budget <= EUR 650,000 (and must not be spent fully).
* Element cost EC_i = base_cost_i + unit_cost_i * area  (Eq. 1).
* Biodiversity = min over {bio-retention, dry swale, extensive GR, intensive GR}
  of the catchment-summed implemented area (Eq. 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import openpyxl

BUDGET_EUR = 650_000.0

# NBS i-index (1..7) follows Table 8 of the Combat description.
GREEN = "green"
ROOF = "roof"
ROAD = "road"


@dataclass(frozen=True)
class NBSType:
    idx: int                 # i = 1..7 (Table 8)
    key: str                 # short key
    swmm_name: str           # exact LID-process name in the .inp
    group: str               # green | roof | road
    base_cost: float         # EUR
    unit_cost: float         # EUR / m2
    binary_area: bool        # roof LIDs may only be full-area or zero
    counts_biodiversity: bool

    def element_cost(self, area: float) -> float:
        return 0.0 if area <= 0 else self.base_cost + self.unit_cost * area


# Order matches the columns of the Excel sheets.
NBS_TYPES: Dict[str, NBSType] = {
    "soakaway": NBSType(1, "soakaway", "Soakaway", GREEN, 608, 1000, False, False),
    "bioretention": NBSType(2, "bioretention", "Bio_retention_system", GREEN, 608, 200, False, True),
    "dryswale": NBSType(3, "dryswale", "Dry_swale", GREEN, 103, 177, False, True),
    "ext_green_roof": NBSType(4, "ext_green_roof", "Extensive_green_roof", ROOF, 486, 25, True, True),
    "int_green_roof": NBSType(5, "int_green_roof", "Intensive_green_roof", ROOF, 486, 46, True, True),
    "cistern": NBSType(6, "cistern", "Cistern", ROOF, 161, 100, True, False),
    "permeable": NBSType(7, "permeable", "Permeable_pavement", ROAD, 344, 70, False, False),
}

# Column order in the Excel sheets (after the Subcatchments column).
EXCEL_COLUMN_ORDER = ["soakaway", "bioretention", "dryswale",
                      "ext_green_roof", "int_green_roof", "cistern", "permeable"]

GROUP_TYPES = {
    GREEN: ["soakaway", "bioretention", "dryswale"],
    ROOF: ["ext_green_roof", "int_green_roof", "cistern"],
    ROAD: ["permeable"],
}

BIODIVERSITY_TYPES = ["bioretention", "dryswale", "ext_green_roof", "int_green_roof"]


@dataclass
class SubcatchmentLimits:
    name: str
    max_area: Dict[str, float]      # key -> max NBS area (m2)
    max_imperv_pct: Dict[str, float]  # key -> max % impervious treated


def parse_subcatchment_geometry(inp_path: str | Path) -> Dict[str, Dict[str, float]]:
    """Return {name: {area_ha, imperv_pct, imperv_m2}} from [SUBCATCHMENTS]."""
    import re
    text = Path(inp_path).read_text()
    m = re.search(r"\[SUBCATCHMENTS\](.*?)\n\[", text, re.S)
    out: Dict[str, Dict[str, float]] = {}
    for line in m.group(1).splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        p = s.split()
        name, area_ha, imperv = p[0], float(p[3]), float(p[4])
        out[name] = {"area_ha": area_ha, "imperv_pct": imperv,
                     "imperv_m2": area_ha * 1e4 * imperv / 100.0}
    return out


def load_limits(impl_xlsx: str | Path) -> Dict[str, SubcatchmentLimits]:
    """Parse implementation_details.xlsx into per-sub-catchment limits."""
    wb = openpyxl.load_workbook(impl_xlsx, data_only=True)
    ws_area = wb["Allowed_NBS (m²)"]
    ws_pct = wb["Allowed_imperviousness_area (%)"]

    def read_sheet(ws) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for row in ws.iter_rows(min_row=3, values_only=True):
            name = row[0]
            if name is None:
                continue
            vals = {}
            for j, key in enumerate(EXCEL_COLUMN_ORDER):
                v = row[1 + j]
                vals[key] = float(v) if v is not None else 0.0
            out[str(name)] = vals
        return out

    areas = read_sheet(ws_area)
    pcts = read_sheet(ws_pct)

    limits: Dict[str, SubcatchmentLimits] = {}
    for name in areas:
        limits[name] = SubcatchmentLimits(
            name=name,
            max_area=areas[name],
            max_imperv_pct=pcts.get(name, {k: 0.0 for k in EXCEL_COLUMN_ORDER}),
        )
    return limits
