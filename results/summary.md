# NBS Combat - Optimised Retrofit Solution

*Model:* `baseline.inp`  |  *decision variables:* 48  |  *SWMM evaluations:* 2400

## Headline result (TOPSIS recommendation)

| KPI | Baseline | Recommended | Change |
|---|---:|---:|---:|
| Weighted flood volume (m³) | 2,233 | 314 | -85.9% |
| Flooding, T10 storm (m³) | 629 | 0 | -100.0% |
| Flooding, T100 storm (m³) | 4,640 | 785 | -83.1% |
| Lifecycle cost (EUR) | 0 | 11,055,601 | - |
| Co-benefit index | 0 | 21,678 | - |
| NBS footprint (m²) | 0 | 44,516 | - |
| Peak outfall flow (m³/s) | 2.16 | 1.97 | -8.8% |

## Alternative non-dominated picks

| Strategy | Cost (EUR) | Weighted flood (m³) | Flood cut | Co-benefit |
|---|---:|---:|---:|---:|
| topsis | 11,055,601 | 314 | -85.9% | 21,678 |
| knee | 4,686,529 | 842 | -62.3% | 10,054 |
| budget | 16,975,486 | 49 | -97.8% | 31,916 |

## Recommended NBS mix (by type)

| NBS type | Total area (m²) |
|---|---:|
| Green roof | 16,065 |
| Bioretention cell / rain garden | 11,613 |
| Rain barrel / cistern | 9,043 |
| Permeable pavement | 7,796 |

## Independent verification storms

Flood volumes for the recommended design across the full storm suite (including the 1-year storm excluded from optimisation):

| Storm | Flood volume (m³) |
|---|---:|
| T1 | 0 |
| T10 | 0 |
| T100 | 784 |

## Top sub-catchment interventions

| Sub-catchment | NBS | Area (m²) | Lifecycle cost (EUR) |
|---|---|---:|---:|
| S8 | Green roof | 4,810 | 1,630,666 |
| S2 | Green roof | 4,754 | 1,611,727 |
| S4 | Green roof | 2,927 | 992,249 |
| S1 | Bioretention cell / rain garden | 2,188 | 589,261 |
| S12 | Green roof | 1,634 | 553,774 |
| S3 | Permeable pavement | 2,862 | 513,697 |
| S12 | Bioretention cell / rain garden | 1,802 | 485,070 |
| S9 | Bioretention cell / rain garden | 1,488 | 400,612 |
| S4 | Permeable pavement | 2,189 | 392,870 |
| S4 | Bioretention cell / rain garden | 1,447 | 389,726 |
| S8 | Bioretention cell / rain garden | 1,207 | 324,954 |
| S3 | Bioretention cell / rain garden | 1,191 | 320,647 |
| S2 | Permeable pavement | 1,392 | 249,784 |
| S5 | Rain barrel / cistern | 2,084 | 249,603 |
| S3 | Green roof | 730 | 247,325 |
