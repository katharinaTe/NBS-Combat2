# Official UDM-2025 NBS Combat — solution method

This documents the solution to the **official** Combat case study (the
participant-only `Case_study_20241121.inp` and `implementation_details.xlsx`),
as distinct from the generic demonstration framework in the repository root.

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
evaluated **once each** with the real SWMM engine over the full year
(`combat_validate.py`, parallel, one process per core with `THREADS=1`). The
seven indicators are computed against the baseline `.rpt` and the variants are
ranked with **TOPSIS** (`combat_report.py`); the top-ranked variant is promoted
to the official `solutions.xlsx` submission.

## Compliance

Every produced solution is checked against all Combat rules before export
(`Solution.validate`): per-group exclusivity, one-type-per-group, binary roof
areas, per-sub-catchment area and %-impervious caps, and the €650,000 budget.
The output is the exact two-sheet `solutions.xlsx` template (`LID_Areas`,
`LID_Percentage_Implemented`) the organisers ingest.
