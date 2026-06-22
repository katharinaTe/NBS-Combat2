"""Generate a reproducible baseline SWMM model for the NBS Combat demo case study.

This writes ``data/case_study/baseline.inp`` -- a small but realistic urban
catchment whose trunk sewer is deliberately under-capacity, so that the design
storms produce surface flooding at several nodes.  The model is intentionally
self-contained and reproducible so the optimisation framework can be exercised
end-to-end without the (participant-only) official Combat dataset.

When the official UDM-2025 ``.inp`` becomes available, drop it in as
``data/case_study/baseline.inp`` and the rest of the pipeline works unchanged.
"""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "case_study" / "baseline.inp"

# --------------------------------------------------------------------------- #
# Catchment definition
# --------------------------------------------------------------------------- #
# A 4 x 3 grid of sub-catchments drains into a branching trunk sewer that ends
# at a single outfall.  Imperviousness rises towards the (downstream) centre to
# mimic a dense urban core surrounded by greener suburbs.
N_COLS, N_ROWS = 4, 3
SUBCATCH_AREA_HA = 2.0           # ha per sub-catchment
GROUND_SLOPE_PCT = 1.5

# Per-subcatchment imperviousness (%) -- denser towards downstream/core.
IMPERV = {
    "S1": 45, "S2": 55, "S3": 62, "S4": 48,
    "S5": 70, "S6": 85, "S7": 80, "S8": 60,
    "S9": 52, "S10": 75, "S11": 78, "S12": 50,
}

SUBCATCHMENTS = list(IMPERV.keys())

# Drainage topology: each sub-catchment -> its inlet junction.
# Junctions form two laterals (J1..J6) and (J7..J12) merging at J_TRUNK -> OUT.
# Downstream trunk conduits are undersized to force flooding.
JUNCTION_ELEV = {}   # node -> invert elevation (m)
LINKS = []           # (name, from, to, length, diameter)


def build_network():
    # Two lateral branches converging at the trunk.
    branch_a = ["J1", "J2", "J3", "J4", "J5", "J6"]
    branch_b = ["J7", "J8", "J9", "J10", "J11", "J12"]
    trunk = "JT"
    outfall = "OUT"

    # Invert elevations descend towards the outfall.
    base = 100.0
    for i, j in enumerate(branch_a):
        JUNCTION_ELEV[j] = base - 0.6 * i
    for i, j in enumerate(branch_b):
        JUNCTION_ELEV[j] = base - 0.6 * i
    JUNCTION_ELEV[trunk] = base - 0.6 * 6 - 0.5
    out_elev = JUNCTION_ELEV[trunk] - 0.8

    # Lateral conduits (well sized, 0.6 m).
    for i in range(len(branch_a) - 1):
        LINKS.append((f"CA{i+1}", branch_a[i], branch_a[i + 1], 120.0, 0.6))
    for i in range(len(branch_b) - 1):
        LINKS.append((f"CB{i+1}", branch_b[i], branch_b[i + 1], 120.0, 0.6))

    # Branch outlets into the trunk node, then trunk -> outfall.
    # The trunk pipes are deliberately undersized (0.75 m) given the load.
    LINKS.append(("CA_T", branch_a[-1], trunk, 90.0, 0.75))
    LINKS.append(("CB_T", branch_b[-1], trunk, 90.0, 0.75))
    LINKS.append(("C_OUT", trunk, outfall, 80.0, 0.75))

    # Sub-catchment -> inlet junction assignment.
    outlet = {
        "S1": "J1", "S2": "J2", "S3": "J3", "S4": "J4",
        "S5": "J5", "S6": "J6", "S7": "J7", "S8": "J8",
        "S9": "J9", "S10": "J10", "S11": "J11", "S12": "J12",
    }
    return branch_a, branch_b, trunk, outfall, out_elev, outlet


# --------------------------------------------------------------------------- #
# Design-storm hyetographs (Chicago design storm)
# --------------------------------------------------------------------------- #
def chicago_hyetograph(total_depth_mm, duration_min=120, dt_min=5, r=0.4,
                       a=None, b=8.0, c=0.75):
    """Return a list of (minute, intensity_mm_per_hr) for a Chicago design storm.

    Uses an IDF of the form i = a / (t + b)**c (t in minutes, i in mm/hr).
    ``a`` is calibrated so the integrated depth matches ``total_depth_mm``.
    """
    dur_h = duration_min / 60.0
    # Calibrate 'a' to hit the target total depth over the duration.
    if a is None:
        # mean intensity required (mm/hr) times duration = depth
        mean_i = total_depth_mm / dur_h
        # average of a/(t+b)^c over duration ~ a * factor; solve for a.
        n = duration_min // dt_min
        factor = sum(1.0 / (((k + 0.5) * dt_min) + b) ** c for k in range(n)) / n
        a = mean_i / factor

    tp = r * duration_min            # time to peak (min)
    series = []
    n = duration_min // dt_min
    for k in range(n):
        t_mid = (k + 0.5) * dt_min
        if t_mid <= tp:
            tt = (tp - t_mid) / r
        else:
            tt = (t_mid - tp) / (1.0 - r)
        i = a / ((tt + b) ** c)
        series.append((k * dt_min, round(i, 2)))
    return series


STORMS = {
    # name: (return-period label, total depth mm, weight in objective)
    "T1":   ("1-year",   28.0, 0.50),
    "T10":  ("10-year",  48.0, 0.35),
    "T100": ("100-year", 78.0, 0.15),
}


# --------------------------------------------------------------------------- #
# .inp assembly
# --------------------------------------------------------------------------- #
def fmt_time(minute):
    h = minute // 60
    m = minute % 60
    return f"{h:d}:{m:02d}"


def build_inp():
    branch_a, branch_b, trunk, outfall, out_elev, outlet = build_network()

    lines = []
    w = lines.append

    w("[TITLE]")
    w("NBS Combat - demonstration urban catchment (reproducible baseline)")
    w("Trunk sewer is under-capacity; design storms cause node flooding.")
    w("")

    w("[OPTIONS]")
    w("FLOW_UNITS           CMS")
    w("INFILTRATION         HORTON")
    w("FLOW_ROUTING         DYNWAVE")
    w("LINK_OFFSETS         DEPTH")
    w("MIN_SLOPE            0")
    w("ALLOW_PONDING        YES")
    w("SKIP_STEADY_STATE    NO")
    w("START_DATE           01/01/2025")
    w("START_TIME           00:00:00")
    w("REPORT_START_DATE    01/01/2025")
    w("REPORT_START_TIME    00:00:00")
    w("END_DATE             01/01/2025")
    w("END_TIME             04:00:00")
    w("SWEEP_START          01/01")
    w("SWEEP_END            12/31")
    w("DRY_DAYS             0")
    w("REPORT_STEP          00:05:00")
    w("WET_STEP             00:01:00")
    w("DRY_STEP             00:05:00")
    w("ROUTING_STEP         0:00:15")
    w("RULE_STEP            00:00:00")
    w("INERTIAL_DAMPING     PARTIAL")
    w("NORMAL_FLOW_LIMITED  BOTH")
    w("FORCE_MAIN_EQUATION  H-W")
    w("VARIABLE_STEP        0.75")
    w("LENGTHENING_STEP     0")
    w("MIN_SURFAREA         1.167")
    w("MAX_TRIALS           8")
    w("HEAD_TOLERANCE       0.0015")
    w("SYS_FLOW_TOL         5")
    w("LAT_FLOW_TOL         5")
    w("MINIMUM_STEP         0.5")
    w("THREADS              1")
    w("")

    w("[EVAPORATION]")
    w(";;Type      Parameters")
    w("CONSTANT    3.0")
    w("DRY_ONLY    NO")
    w("")

    # Single rain gage; the active storm time series is swapped at run time by
    # the model wrapper (it rewrites the [RAINGAGES] source line).
    w("[RAINGAGES]")
    w(";;Name  Format    Interval  SCF  Source")
    w("RG1     INTENSITY 0:05      1.0  TIMESERIES TS_T10")
    w("")

    w("[SUBCATCHMENTS]")
    w(";;Name  RainGage  Outlet  Area  %Imperv  Width  %Slope  CurbLen")
    for s in SUBCATCHMENTS:
        area = SUBCATCH_AREA_HA
        width = round(math.sqrt(area * 10000) * 1.2, 1)  # flow width (m)
        w(f"{s:6s}  RG1       {outlet[s]:6s}  {area:.2f}  {IMPERV[s]:5d}  "
          f"{width:6.1f}  {GROUND_SLOPE_PCT:.2f}  0")
    w("")

    w("[SUBAREAS]")
    w(";;Subcat  N-Imperv  N-Perv  S-Imperv  S-Perv  PctZero  RouteTo")
    for s in SUBCATCHMENTS:
        w(f"{s:6s}  0.013     0.10    1.5       5.0     25       OUTLET")
    w("")

    w("[INFILTRATION]")
    w(";;Subcat  MaxRate  MinRate  Decay  DryTime  MaxInfil")
    for s in SUBCATCHMENTS:
        w(f"{s:6s}  75.0     8.0      4.0    7        0")
    w("")

    w("[JUNCTIONS]")
    w(";;Name  Elev  MaxDepth  InitDepth  SurDepth  Aponded")
    for j, elev in JUNCTION_ELEV.items():
        # 3 m deep manholes; allow generous ponding area (m2) so floods register.
        w(f"{j:6s}  {elev:.2f}  3.0       0          0         2000")
    w("")

    w("[OUTFALLS]")
    w(";;Name  Elev  Type  Gated")
    w(f"{outfall:6s}  {out_elev:.2f}  FREE  NO")
    w("")

    w("[CONDUITS]")
    w(";;Name  FromNode  ToNode  Length  Roughness  InOffset  OutOffset  InitFlow  MaxFlow")
    for name, fn, tn, length, _dia in LINKS:
        w(f"{name:6s}  {fn:6s}  {tn:6s}  {length:6.1f}  0.013      0         0          0         0")
    w("")

    w("[XSECTIONS]")
    w(";;Link  Shape     Geom1  Geom2  Geom3  Geom4  Barrels")
    for name, _fn, _tn, _length, dia in LINKS:
        w(f"{name:6s}  CIRCULAR  {dia:.3f}  0      0      0      1")
    w("")

    # Time series for all design storms (the wrapper points the gage at one).
    w("[TIMESERIES]")
    w(";;Name  Time   Value")
    for key, (_label, depth, _wt) in STORMS.items():
        series = chicago_hyetograph(depth)
        for minute, inten in series:
            w(f"TS_{key:5s}  {fmt_time(minute):6s}  {inten}")
        w(";")
    w("")

    w("[REPORT]")
    w("INPUT      NO")
    w("CONTROLS   NO")
    w("SUBCATCHMENTS ALL")
    w("NODES      ALL")
    w("LINKS      ALL")
    w("")

    # Minimal coordinates so the file is GUI-friendly (optional for solver).
    w("[COORDINATES]")
    w(";;Node  X  Y")
    coords = {}
    for i, j in enumerate(branch_a):
        coords[j] = (i * 100.0, 200.0)
    for i, j in enumerate(branch_b):
        coords[j] = (i * 100.0, 0.0)
    coords[trunk] = (650.0, 100.0)
    coords[outfall] = (750.0, 100.0)
    for node, (x, y) in coords.items():
        w(f"{node:6s}  {x:.1f}  {y:.1f}")
    w("")

    w("[SYMBOLS]")
    w(";;Gage  X  Y")
    w("RG1     -50.0  100.0")
    w("")

    return "\n".join(lines) + "\n"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_inp())
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print("Sub-catchments:", len(SUBCATCHMENTS))
    print("Storms:", {k: v[0] for k, v in STORMS.items()})


if __name__ == "__main__":
    main()
