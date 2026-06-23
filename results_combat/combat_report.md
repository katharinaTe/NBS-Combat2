# NBS Combat - Optimised Solution (official case study)

Seven indicators ranked by TOPSIS, evaluated with SWMM 5.2 on the **20 Aug-3 Sep 2018 storm window (warm-up from 20 Aug, evaluation from 22 Aug)**. Cost and biodiversity are period-independent; the five hydraulic/quality indicators below are computed on this window and used to *rank* the strategy variants. The organisers score the submitted solution on the full year.

## Baseline (no NBS)

- Flooding loss V_F: **0.021** (10⁶ L)
- Evaporation loss E: **0.760**
- WWTP inflow volume: **18.905** (10⁶ L)
- CSO overflow volume V_CSO: **13.157** (10⁶ L)
- CSO TSS load M_TSS: **1,030.6** (kg)

## Strategy variants - seven indicators

| Variant | Cost € | Biodiv. m² | ΔV_F flood↓ | ΔE evap↑ | ΔWWTP↑ | ΔCSO↓ | ΔTSS↓ kg | TOPSIS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| biodiverse ⭐ | 640,038 | 600 | 0.013 | 0.042 | 0.987 | 1.801 | 149.6 | 0.744 |
| balanced | 640,114 | 300 | 0.014 | 0.040 | 0.981 | 1.929 | 174.6 | 0.611 |
| capture | 640,029 | 0 | 0.018 | 0.016 | 0.831 | 2.340 | 218.8 | 0.446 |
| thrifty | 443,248 | 300 | 0.004 | 0.037 | 0.439 | 1.272 | 99.9 | 0.378 |

**Recommended submission: `biodiverse`** (highest TOPSIS across the seven indicators).

## Recommended solution composition

- Total cost: €640,038 of €650,000 budget
- Biodiversity indicator: 600.0 m²
- Interventions: 299 across 280 sub-catchments
- Area by NBS type (m²):
    - bioretention: 600.0
    - dryswale: 600.0
    - ext_green_roof: 2,568.0
    - int_green_roof: 2,303.0
    - cistern: 259.0
    - permeable: 1,752.7
