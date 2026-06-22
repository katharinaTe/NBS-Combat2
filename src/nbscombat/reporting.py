"""Plots and written report for an optimisation run."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .nbs_catalog import CATALOG


def plot_pareto(F: np.ndarray, picks: Dict[str, int], out_path: Path):
    """Cost vs flood scatter, coloured by co-benefit, with highlighted picks."""
    flood, cost, neg_cb = F[:, 0], F[:, 1] / 1e6, -F[:, 2]
    fig, ax = plt.subplots(figsize=(8, 6))
    sc = ax.scatter(cost, flood, c=neg_cb, cmap="viridis", s=45,
                    edgecolor="k", linewidth=0.3, alpha=0.85)
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label("Co-benefit index (higher = better)")
    markers = {"topsis": ("*", "red", "TOPSIS recommendation"),
               "knee": ("D", "orange", "Knee point"),
               "budget": ("s", "magenta", "Budget-optimal (90% cut)")}
    for name, idx in picks.items():
        if idx is None:
            continue
        mk, col, lab = markers.get(name, ("o", "black", name))
        ax.scatter(cost[idx], flood[idx], marker=mk, s=260, c=col,
                   edgecolor="k", linewidth=1.0, label=lab, zorder=5)
    ax.set_xlabel("Lifecycle cost (million EUR)")
    ax.set_ylabel("Weighted design-storm flooding (m³)")
    ax.set_title("NBS retrofit Pareto front (cost vs flooding vs co-benefit)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_flood_reduction(baseline: Dict[str, float], recommended: Dict[str, float],
                         out_path: Path):
    storms = list(baseline.keys())
    x = np.arange(len(storms))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(x - w / 2, [baseline[s] for s in storms], w, label="Baseline",
           color="#c0392b")
    ax.bar(x + w / 2, [recommended[s] for s in storms], w, label="Recommended NBS",
           color="#27ae60")
    ax.set_xticks(x)
    ax.set_xticklabels(storms)
    ax.set_ylabel("Node flooding volume (m³)")
    ax.set_title("Flood volume by design storm: baseline vs recommended")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def write_design_csv(rows: List[dict], out_path: Path):
    if not rows:
        out_path.write_text("subcatchment,nbs,type,area_m2,capital_eur,lifecycle_eur\n")
        return
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, *, model_name: str, n_var: int, n_evals: int,
                  baseline_kpi, recommended_kpi, recommended_rows,
                  picks_kpi: Dict[str, object], verification: Dict[str, float]):
    def pct(base, new):
        return 0.0 if base <= 0 else 100.0 * (base - new) / base

    by_type: Dict[str, float] = {}
    for r in recommended_rows:
        by_type[r["type"]] = by_type.get(r["type"], 0.0) + r["area_m2"]

    lines = []
    a = lines.append
    a("# NBS Combat - Optimised Retrofit Solution\n")
    a(f"*Model:* `{model_name}`  |  *decision variables:* {n_var}  "
      f"|  *SWMM evaluations:* {n_evals}\n")

    a("## Headline result (TOPSIS recommendation)\n")
    a("| KPI | Baseline | Recommended | Change |")
    a("|---|---:|---:|---:|")
    a(f"| Weighted flood volume (m³) | {baseline_kpi.flood_weighted:,.0f} | "
      f"{recommended_kpi.flood_weighted:,.0f} | "
      f"-{pct(baseline_kpi.flood_weighted, recommended_kpi.flood_weighted):.1f}% |")
    for s in baseline_kpi.flood_by_storm:
        b = baseline_kpi.flood_by_storm[s]
        n = recommended_kpi.flood_by_storm[s]
        a(f"| Flooding, {s} storm (m³) | {b:,.0f} | {n:,.0f} | -{pct(b, n):.1f}% |")
    a(f"| Lifecycle cost (EUR) | 0 | {recommended_kpi.cost:,.0f} | - |")
    a(f"| Co-benefit index | 0 | {recommended_kpi.cobenefit:,.0f} | - |")
    a(f"| NBS footprint (m²) | 0 | {recommended_kpi.footprint:,.0f} | - |")
    a(f"| Peak outfall flow (m³/s) | {baseline_kpi.peak_outflow:.2f} | "
      f"{recommended_kpi.peak_outflow:.2f} | "
      f"-{pct(baseline_kpi.peak_outflow, recommended_kpi.peak_outflow):.1f}% |\n")

    a("## Alternative non-dominated picks\n")
    a("| Strategy | Cost (EUR) | Weighted flood (m³) | Flood cut | Co-benefit |")
    a("|---|---:|---:|---:|---:|")
    for name, kpi in picks_kpi.items():
        if kpi is None:
            a(f"| {name} | - | (no design meets target) | - | - |")
            continue
        a(f"| {name} | {kpi.cost:,.0f} | {kpi.flood_weighted:,.0f} | "
          f"-{pct(baseline_kpi.flood_weighted, kpi.flood_weighted):.1f}% | "
          f"{kpi.cobenefit:,.0f} |")
    a("")

    a("## Recommended NBS mix (by type)\n")
    a("| NBS type | Total area (m²) |")
    a("|---|---:|")
    for t, area in sorted(by_type.items(), key=lambda kv: -kv[1]):
        a(f"| {CATALOG[t].name} | {area:,.0f} |")
    a("")

    a("## Independent verification storms\n")
    a("Flood volumes for the recommended design across the full storm suite "
      "(including the 1-year storm excluded from optimisation):\n")
    a("| Storm | Flood volume (m³) |")
    a("|---|---:|")
    for s, v in verification.items():
        a(f"| {s} | {v:,.0f} |")
    a("")

    a("## Top sub-catchment interventions\n")
    a("| Sub-catchment | NBS | Area (m²) | Lifecycle cost (EUR) |")
    a("|---|---|---:|---:|")
    for r in sorted(recommended_rows, key=lambda r: -r["lifecycle_eur"])[:15]:
        a(f"| {r['subcatchment']} | {r['nbs']} | {r['area_m2']:,.0f} | "
          f"{r['lifecycle_eur']:,.0f} |")
    a("")

    path.write_text("\n".join(lines))
