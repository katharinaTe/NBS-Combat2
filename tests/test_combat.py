"""Unit tests for the NBS Combat logic that do not require a SWMM run.

Run with:  PYTHONPATH=src python -m pytest tests/test_combat.py
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nbscombat.combat_data import NBS_TYPES, BUDGET_EUR, BIODIVERSITY_TYPES
from nbscombat.combat_model import Solution, parse_rpt
from nbscombat import combat_report


def test_element_cost_matches_equation_1():
    # EC = base + unit * area  (Table 8: bio-retention base 608, unit 200)
    t = NBS_TYPES["bioretention"]
    assert t.element_cost(0) == 0
    assert t.element_cost(50) == pytest.approx(608 + 200 * 50)


def test_total_cost_sums_elements():
    sol = Solution()
    sol.add(".1", "dryswale", 10, 100)        # 103 + 177*10 = 1873
    sol.add(".2", "permeable", 20, 50)        # 344 + 70*20  = 1744
    assert sol.total_cost() == pytest.approx(1873 + 1744)


def test_biodiversity_is_min_over_four_types():
    sol = Solution()
    sol.add(".1", "bioretention", 100, 100)
    sol.add(".2", "dryswale", 50, 100)
    sol.add(".3", "ext_green_roof", 200, 100)
    sol.add(".4", "int_green_roof", 80, 100)
    # min(100, 50, 200, 80) = 50 ; soakaway/cistern/permeable excluded
    assert sol.biodiversity() == pytest.approx(50)
    sol.add(".5", "soakaway", 999, 100)       # must not affect biodiversity
    assert sol.biodiversity() == pytest.approx(50)


def test_biodiversity_zero_when_a_type_missing():
    sol = Solution()
    sol.add(".1", "bioretention", 100, 100)
    sol.add(".2", "dryswale", 100, 100)
    sol.add(".3", "ext_green_roof", 100, 100)
    # int_green_roof missing -> min includes 0
    assert sol.biodiversity() == 0


def test_one_type_per_group_overwrites():
    sol = Solution()
    sol.add(".1", "bioretention", 100, 100)
    sol.add(".1", "dryswale", 50, 100)        # same green group -> replaces
    groups = sol.placements[".1"]
    assert set(g for g in groups) == {"green"}
    assert groups["green"].nbs_key == "dryswale"


def test_validation_flags_budget_and_area():
    sol = Solution()
    # area beyond any sane max with a fake limit
    from nbscombat.combat_data import SubcatchmentLimits
    limits = {".1": SubcatchmentLimits(".1",
              max_area={k: 10 for k in NBS_TYPES},
              max_imperv_pct={k: 100 for k in NBS_TYPES})}
    sol.add(".1", "bioretention", 50, 100)    # exceeds max_area 10
    errs = sol.validate(limits)
    assert any("area" in e for e in errs)


def test_topsis_prefers_dominant_row():
    # rows: [cost(min), biodiv, flood, evap, wwtp, cso, tss] all 'max' but cost
    base = combat_report.Indicators(cost=600000, biodiversity=0,
        flood_reduction=0, evaporation_gain=0, wwtp_increase=0,
        cso_reduction=0, tss_reduction=0)
    good = combat_report.Indicators(cost=400000, biodiversity=500,
        flood_reduction=10, evaporation_gain=5, wwtp_increase=2,
        cso_reduction=8, tss_reduction=300)
    ranking = combat_report.rank_variants({"base": base, "good": good})
    assert ranking[0][0] == "good"


def test_rpt_parser_reads_indicators():
    fake = """
  Runoff Quantity Continuity     hectare-m       mm
  Evaporation Loss .........         3.210       4.560
  Flow Routing Continuity        hectare-m      10^6 ltr
  Flooding Loss ............         1.234        12.340
  Outfall Loading Summary
  Outfall Node           Pcnt       LPS       LPS      10^6 ltr    kg
  CSO_overflow           12.34    123.45   1234.56      45.678    2345.6
  WWTP                   88.00     25.00     30.00      33.210     123.4
"""
    k = parse_rpt(fake, cost=1.0, biodiversity=2.0)
    assert k.flood_volume == pytest.approx(1.234)
    assert k.evaporation == pytest.approx(3.21)
    assert k.wwtp_volume == pytest.approx(33.21)
    assert k.cso_volume == pytest.approx(45.678)
    assert k.cso_tss == pytest.approx(2345.6)
