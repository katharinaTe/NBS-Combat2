"""Full-year SWMM validation of candidate solutions.

A single full-year run of the official case study takes >10 minutes, so the
optimiser never calls SWMM. This module is the separate, opt-in validation step:
it writes each candidate solution into the official ``.inp`` and runs the SWMM
engine to extract the true seven Combat indicators from the ``.rpt`` file.

Validations run in parallel (one process per core, THREADS forced to 1 so the
processes do not over-subscribe the CPU), which lets a small set of strategy
variants plus the baseline be evaluated in roughly the wall-clock time of one
4-thread run.
"""
from __future__ import annotations

import multiprocessing as mp
import re
import shutil
from pathlib import Path
from typing import Dict, Optional

from .combat_model import CombatKPIs, Solution, parse_rpt


def _prepare_workdir(base_inp: Path, workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    for dat in ("rain2018.dat", "temp2018.dat"):
        src = base_inp.parent / dat
        dst = workdir / dat
        if src.exists() and not dst.exists():
            try:
                dst.symlink_to(src.resolve())
            except OSError:
                shutil.copy(src, dst)


def _write_variant_inp(base_text: str, sol: Solution, path: Path,
                       threads: int = 1):
    block = ("[LID_USAGE]\n"
             ";;Subcatchment   LID Process      Number  Area       Width"
             "      InitSat    FromImp    ToPerv\n")
    block += sol.lid_usage_lines() + "\n"
    text = re.sub(r"\[LID_USAGE\][^\[]*", block + "\n", base_text, count=1)
    text = re.sub(r"THREADS\s+\d+", f"THREADS              {threads}", text)
    path.write_text(text)


def _run_one(args) -> tuple:
    """Worker: write + run + parse one variant. Returns (name, kpis|errstr)."""
    import os
    from pyswmm import Simulation
    name, base_inp_str, base_text, sol, root_str, cost, biodiversity = args
    base_inp = Path(base_inp_str)
    workdir = Path(root_str) / name
    _prepare_workdir(base_inp, workdir)
    inp = workdir / f"{name}.inp"
    _write_variant_inp(base_text, sol, inp, threads=1)
    cwd = os.getcwd()
    try:
        os.chdir(workdir)
        with Simulation(inp.name) as sim:
            for _ in sim:
                pass
    except Exception as e:  # noqa: BLE001
        os.chdir(cwd)
        return name, f"ERROR: {e}"
    finally:
        os.chdir(cwd)
    rpt = inp.with_suffix(".rpt")
    kpis = parse_rpt(rpt.read_text(), cost=cost, biodiversity=biodiversity)
    return name, kpis


def validate_solutions(base_inp: str | Path, solutions: Dict[str, Solution],
                       root: str | Path, n_parallel: int = 4
                       ) -> Dict[str, CombatKPIs]:
    base_inp = Path(base_inp)
    base_text = base_inp.read_text()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    tasks = [(name, str(base_inp), base_text, sol, str(root),
              sol.total_cost(), sol.biodiversity())
             for name, sol in solutions.items()]
    results: Dict[str, CombatKPIs] = {}
    if n_parallel <= 1 or len(tasks) == 1:
        for t in tasks:
            name, res = _run_one(t)
            results[name] = res
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(min(n_parallel, len(tasks))) as pool:
            for name, res in pool.imap_unordered(_run_one, tasks):
                results[name] = res
    return results
