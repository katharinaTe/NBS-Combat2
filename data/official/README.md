# Official Combat case-study data

The official UDM-2025 NBS Combat materials are distributed to registered
participants only, so the raw files are **not redistributed** in this repository
(see `.gitignore`). To run the official solver, place these files here:

| File | Description |
|---|---|
| `Case_study.inp` | calibrated SWMM 5.2 combined-sewer model (805 sub-catchments, CSO + WWTP) |
| `rain2018.dat` | 1-minute precipitation series, 2018 |
| `temp2018.dat` | 10-minute temperature series, 2018 |
| `implementation_details.xlsx` | per-sub-catchment allowed NBS areas (m²) and %-impervious caps |
| `solutions_template.xlsx` | official two-sheet submission template |

Download from <https://www.uibk.ac.at/en/congress/udm2025/>.

Then run:

```bash
python scripts/solve_combat.py            # construct variants (fast)
python scripts/solve_combat.py --validate # + full-year SWMM validation (slow)
```
