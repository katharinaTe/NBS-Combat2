# Official UDM-2025 NBS Combat — solution method

This documents the solution to the **official** Combat case study (the
participant-only `Case_study_20241121.inp` and `implementation_details.xlsx`),
as distinct from the generic demonstration framework in the repository root.

## Competing against the published team results

The organisers' `PerformanceIndicator_Teams.xlsx` gives the six teams' full-year
indicators. Their TOPSIS (equal weights, organisers' method):

| Team | Cost € | Biodiv. | Flood | Evap | WWTP | CSO | TSS | TOPSIS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Team 1 | 648,895 | 1251 | 0.297 | 8.82 | 6.32 | 25.13 | 1986.6 | **0.903** |
| Team 2 | 649,030 | 1207 | 0.288 | 9.29 | 6.71 | 16.76 | 1324.8 | 0.780 |
| Team 3 | 627,744 | 974 | 0.295 | 6.68 | 7.57 | 15.94 | 1796.4 | 0.774 |
| Team 4 | 639,352 | 1269 | 0.297 | 8.45 | 4.34 | 24.36 | 1889.2 | 0.764 |
| Team 5 | 626,695 | 1213 | 0.295 | 8.07 | -2.08 | 22.33 | 1742.7 | 0.445 |
| Team 6 | 640,020 | 0 | 0.184 | 5.16 | -0.64 | 10.69 | 819.5 | 0.107 |

Two lessons drive the strategy:

* **Biodiversity is decisive.** Team 6 maximised hydraulics but scored zero
  biodiversity (`min` over the four green types) and finished last. Every strong
  entry sits at biodiversity ~1200–1270.
* **Biodiversity and capture are synergistic, not opposed.** Bio-retention and
  dry swale treat 100% of a sub-catchment's impervious area, so the green LIDs
  that earn biodiversity *are* the CSO/TSS/flood capture — the leaders are strong
  on both at once.

Our `competition_solution` targets exactly this: biodiversity **1270 m²**
(higher than every team; Team 4's 1269 was the previous best) at **€643,492**
(below the TOPSIS leader's €648,895), with the green LIDs placed in the
highest-impervious sub-catchments so the same area drives capture. See
`results_combat/teams_comparison.txt` for the head-to-head TOPSIS.

## The problem, precisely

Retrofit a real **combined** sewer network (12.4 km, 805 sub-catchments, one CSO
tank of 154.5 m³ with a 30 L/s throttle to the WWTP and an overflow weir to the
river) with seven predefined NBS, evaluated by **continuous simulation over the
full 2018 year** (1-min rain, 10-min temperature) in SWMM 5.2.

### Seven NBS in three groups

| Group | NBS | SWMM LID | Base € | Unit €/m² | Area rule |
|---|---|---|---:|---:|---|
| Green (treats all impervious) | Soakaway | BC | 608 | 1000 | 0…max |
| | Bio-retention system | BC | 608 | 200 | 0…max |
| | Dry swale | RG | 103 | 177 | 0…max |
| Roof (treats roof runoff) | Extensive green roof | GR | 486 | 25 | full or 0 |
| | Intensive green roof | GR | 486 | 46 | full or 0 |
| | Cistern | RB | 161 | 100 | full or 0 |
| Road (treats access-road runoff) | Permeable pavement | BC | 344 | 70 | 0…max |

Per sub-catchment: at most **one green + one roof + one road** LID, only **one
type per group**, roof LIDs **binary** (full allowed area or none). The allowed
maximum area and maximum % impervious treated per sub-catchment come from
`implementation_details.xlsx`.

### Seven ranked indicators (TOPSIS)

1. **Total cost ↓** — `Σ (base_i + unit_i · area_ij)`, hard cap **€650,000**.
2. **Biodiversity ↑** — `min(ΣA_bioretention, ΣA_dryswale, ΣA_extGR, ΣA_intGR)`.
3. **Flood reduction ΔV_F ↑** — *Flooding Loss* (Flow Routing Continuity).
4. **Evaporation gain ΔE ↑** — *Evaporation Loss* (Runoff Quantity Continuity).
5. **WWTP inflow increase ΔV_WWTP ↑** — *Total Volume* at outfall `WWTP`.
6. **CSO reduction ΔV_CSO ↑** — *Total Volume* at outfall `CSO_overflow`.
7. **TSS reduction ΔM_TSS ↑** — *Total TSS* at outfall `CSO_overflow`.

Indicators 3–7 are **changes versus the no-NBS baseline**; the organisers rank
teams across all seven with TOPSIS.

## Why a metaheuristic is the wrong tool here

One full-year run of the official model takes **>10 minutes** (5-second
dynamic-wave routing, 805 sub-catchments). NSGA-II with thousands of evaluations
would need weeks. We therefore exploit the problem's structure instead.

## Method: structure-aware cost-effectiveness optimisation

Each LID mainly **disconnects impervious runoff from its own sub-catchment**, so
the benefit indicators are approximately separable across sub-catchments. This
makes a transparent, simulation-free greedy on *retained runoff per euro*
extremely effective.

**Two key modelling decisions:**

* **% impervious treated = the allowed maximum.** It is cost-free (cost depends
  only on area, Eq. 1) and weakly increases every benefit indicator, so it is
  dominant — set it to the cap everywhere.
* **Auto-sized footprints.** An LID of area `A` treating impervious area `T`
  retains about `min(T·R, A·K_type)` per year (`R` = annual impervious-runoff
  depth; `K_type` = annual depth the LID processes per m², read from the .inp
  storage/soil/infiltration parameters). This yields an optimal footprint
  `A* = T·R / K_type`, so continuous LIDs are sized to their load rather than
  blindly maximised — freeing budget for wider coverage.

**Two-phase budgeted greedy** (`combat_optimize.py`):

1. *Biodiversity seeding* — raise each of the four biodiversity types to a target
   area `B` using the cheapest-per-m² installations (continuous types part-sized
   to hit `B` exactly; roof types installed full-area). Because the indicator is
   a `min`, this is the only way to lift it, and the binding cost is the
   green-area types.
2. *Capture fill* — spend the remaining budget on the highest
   retained-runoff-per-euro installations (typically cisterns, bio-retention and
   permeable pavement), honouring the one-per-group rule.

Sweeping `B` traces the biodiversity ↔ hydraulic-capture trade-off and yields a
small set of **strategy variants**:

| Variant | `bio_target` | Idea |
|---|---|---|
| `capture` | 0 | maximise hydraulic/CSO/TSS benefits, biodiversity = 0 |
| `balanced` | 300 | strong benefits **and** meaningful biodiversity |
| `biodiverse` | 600 | biodiversity-led |
| `thrifty` | 300 (≤€450k) | spends less → stronger cost indicator |

## Validation and selection

The variants — all rule-checked and budget-feasible by construction — are then
evaluated **once each** with the real SWMM engine (`combat_validate.py`). One
full-year run of the official model takes **>1 hour** (dynamic-wave timestep
collapse), which is impractical for comparing several designs, so the variants
are ranked on a **storm-rich surrogate window** (20 Aug–3 Sep 2018, the wettest
fortnight, with a warm-up and a trimmed rain/temperature file) where a run takes
~2.5 min. Cost and biodiversity are period-independent; the five hydraulic /
quality indicators are computed against the baseline `.rpt` and the variants are
ranked with **TOPSIS** (`combat_report.py`). The window is used only to *select*
which design to submit — the organisers re-score the submitted `solutions.xlsx`
on the full year.

### Validated outcome

Against the no-NBS baseline, every benefit indicator moves the right way. TOPSIS
ranking over the seven indicators:

| Variant | Cost € | Biodiv. m² | Flood ↓ | Evap ↑ | WWTP ↑ | CSO ↓ | TSS ↓ kg | TOPSIS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **biodiverse** ⭐ | 640,038 | 600 | 0.013 | 0.042 | 0.987 | 1.801 | 149.6 | **0.744** |
| balanced | 640,114 | 300 | 0.014 | 0.040 | 0.981 | 1.929 | 174.6 | 0.611 |
| capture | 640,029 | 0 | 0.018 | 0.016 | 0.831 | 2.340 | 218.8 | 0.446 |
| thrifty | 443,248 | 300 | 0.004 | 0.037 | 0.439 | 1.272 | 99.9 | 0.378 |

`capture` wins the raw hydraulic-removal indicators but its zero biodiversity
collapses its TOPSIS score, so the balanced **`biodiverse`** design is promoted
to `solution_SUBMIT.xlsx` (€640,038 = 98.5% of budget, biodiversity 600 m², 299
interventions, 0 rule violations).

### A note on parallelism

`combat_validate.py` launches one process per design, but the bundled SWMM
engine effectively serialises concurrent runs (shared scratch state), so the
batch runs sequentially in practice; with ~2.5-min surrogate runs this is not a
bottleneck.

## Compliance

Every produced solution is checked against all Combat rules before export
(`Solution.validate`): per-group exclusivity, one-type-per-group, binary roof
areas, per-sub-catchment area and %-impervious caps, and the €650,000 budget.
The output is the exact two-sheet `solutions.xlsx` template (`LID_Areas`,
`LID_Percentage_Implemented`) the organisers ingest.
