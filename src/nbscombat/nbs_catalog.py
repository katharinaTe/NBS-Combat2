"""Catalogue of Nature-Based Solutions (NBS) modelled as SWMM LID controls.

Each NBS maps onto an EPA-SWMM Low-Impact-Development (LID) process and carries:

* the ``LID_CONTROLS`` parameter block (validated against the SWMM engine);
* engineering placement rules -- which part of a sub-catchment it consumes
  (impervious "roof/pavement" vs pervious land) and how much upstream
  impervious runoff one unit treats;
* economics -- capital cost and present-value O&M per m²;
* a multi-criteria co-benefit profile (amenity, biodiversity, evapotranspiration
  / urban-cooling, carbon) scored 0-1 per m² of footprint.

The four-type default palette (bioretention, green roof, permeable pavement,
rain barrel) covers the dominant retrofit levers in a dense catchment; the
catalogue is data-driven so adding swales, trenches, etc. is a dict entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class NBS:
    key: str
    name: str
    swmm_process: str          # SWMM LID type code (BC, GR, PP, RB, IT, VS)
    lid_control_block: str     # exact [LID_CONTROLS] text for this process

    # --- placement / hydrology -------------------------------------------- #
    # Which sub-catchment resource the footprint draws from:
    #   "impervious" -> sits on roof/pavement (green roof, permeable pavement)
    #   "pervious"   -> occupies land and treats upstream impervious runoff
    surface: str
    # Fraction of the *source* area in a sub-catchment that may be converted to
    # this NBS (suitability ceiling, 0-1).
    max_area_fraction: float
    # Per unit footprint area, the % of the sub-catchment's impervious runoff
    # that one m² of this NBS intercepts (used to set LID_USAGE FromImp).
    capture_per_m2: float
    # Route LID outflow back onto pervious area (1) or to the outlet (0).
    to_pervious: int

    # --- economics (EUR) --------------------------------------------------- #
    capital_eur_m2: float
    om_eur_m2_yr: float

    # --- co-benefits (score 0-1 per m²) --------------------------------- #
    cobenefit: Dict[str, float] = field(default_factory=dict)

    def lifecycle_cost_m2(self, years: int = 20, discount: float = 0.03) -> float:
        """Capital + present value of O&M over the appraisal period."""
        if discount <= 0:
            pv_factor = years
        else:
            pv_factor = (1 - (1 + discount) ** -years) / discount
        return self.capital_eur_m2 + self.om_eur_m2_yr * pv_factor

    def cobenefit_score_m2(self, weights: Dict[str, float]) -> float:
        return sum(self.cobenefit.get(k, 0.0) * w for k, w in weights.items())


# --------------------------------------------------------------------------- #
# LID_CONTROLS parameter blocks (SWMM 5.2 syntax, metric units)
# --------------------------------------------------------------------------- #
_BC_BLOCK = """\
BC                BC
BC                SURFACE    150        0.0        0.1        1.0        5.0
BC                SOIL       600        0.5        0.2        0.1        50.0       10.0       3.5
BC                STORAGE    450        0.75       8.0        0.0
BC                DRAIN      1.5        0.5        6          6          0          0
"""

_GR_BLOCK = """\
GR                GR
GR                SURFACE    50         0.0        0.1        1.0        5.0
GR                SOIL       150        0.5        0.2        0.1        100.0      10.0       3.5
GR                DRAINMAT   50         0.5        0.1
"""

_PP_BLOCK = """\
PP                PP
PP                SURFACE    6          0.0        0.012      1.0        5.0
PP                PAVEMENT   150        0.15       0.0        500.0      0
PP                STORAGE    450        0.6        12.0       0.0
PP                DRAIN      1.0        0.5        0          6          0          0
"""

_RB_BLOCK = """\
RB                RB
RB                STORAGE    1000       0.75       0.0        0.0
RB                DRAIN      0.8        0.5        0          12         0          0
"""

# Extension palette (defined but not in the default active set) -------------- #
_IT_BLOCK = """\
IT                IT
IT                SURFACE    100        0.0        0.1        1.0        5.0
IT                STORAGE    900        0.6        12.0       0.0
IT                DRAIN      1.0        0.5        6          6          0          0
"""

_VS_BLOCK = """\
VS                VS
VS                SURFACE    250        0.0        0.2        2.0        4.0
"""


CATALOG: Dict[str, NBS] = {
    "BC": NBS(
        key="BC", name="Bioretention cell / rain garden", swmm_process="BC",
        lid_control_block=_BC_BLOCK,
        surface="pervious", max_area_fraction=0.20, capture_per_m2=0.020,
        to_pervious=0,
        capital_eur_m2=180.0, om_eur_m2_yr=6.0,
        cobenefit={"amenity": 0.8, "biodiversity": 0.9,
                   "cooling": 0.7, "carbon": 0.5},
    ),
    "GR": NBS(
        key="GR", name="Green roof", swmm_process="GR",
        lid_control_block=_GR_BLOCK,
        surface="impervious", max_area_fraction=0.45, capture_per_m2=0.0,
        to_pervious=0,
        capital_eur_m2=220.0, om_eur_m2_yr=8.0,
        cobenefit={"amenity": 0.5, "biodiversity": 0.6,
                   "cooling": 0.8, "carbon": 0.6},
    ),
    "PP": NBS(
        key="PP", name="Permeable pavement", swmm_process="PP",
        lid_control_block=_PP_BLOCK,
        surface="impervious", max_area_fraction=0.40, capture_per_m2=0.0,
        to_pervious=0,
        capital_eur_m2=120.0, om_eur_m2_yr=4.0,
        cobenefit={"amenity": 0.3, "biodiversity": 0.2,
                   "cooling": 0.3, "carbon": 0.2},
    ),
    "RB": NBS(
        key="RB", name="Rain barrel / cistern", swmm_process="RB",
        lid_control_block=_RB_BLOCK,
        surface="impervious", max_area_fraction=0.15, capture_per_m2=0.040,
        to_pervious=1,
        capital_eur_m2=90.0, om_eur_m2_yr=2.0,
        cobenefit={"amenity": 0.1, "biodiversity": 0.1,
                   "cooling": 0.1, "carbon": 0.1},
    ),
    "IT": NBS(
        key="IT", name="Infiltration trench", swmm_process="IT",
        lid_control_block=_IT_BLOCK,
        surface="pervious", max_area_fraction=0.10, capture_per_m2=0.030,
        to_pervious=0,
        capital_eur_m2=110.0, om_eur_m2_yr=3.0,
        cobenefit={"amenity": 0.2, "biodiversity": 0.4,
                   "cooling": 0.3, "carbon": 0.2},
    ),
    "VS": NBS(
        key="VS", name="Vegetated swale", swmm_process="VS",
        lid_control_block=_VS_BLOCK,
        surface="pervious", max_area_fraction=0.12, capture_per_m2=0.015,
        to_pervious=1,
        capital_eur_m2=70.0, om_eur_m2_yr=3.0,
        cobenefit={"amenity": 0.4, "biodiversity": 0.7,
                   "cooling": 0.5, "carbon": 0.4},
    ),
}

# Default active palette used by the optimiser.
DEFAULT_PALETTE = ["BC", "GR", "PP", "RB"]

# Co-benefit weighting used to collapse the profile into a single index.
COBENEFIT_WEIGHTS = {"amenity": 0.30, "biodiversity": 0.30,
                     "cooling": 0.25, "carbon": 0.15}


def lid_controls_section(palette=DEFAULT_PALETTE) -> str:
    """Assemble the full [LID_CONTROLS] section for the active palette."""
    blocks = [CATALOG[k].lid_control_block for k in palette]
    return "[LID_CONTROLS]\n" + "\n".join(blocks)
