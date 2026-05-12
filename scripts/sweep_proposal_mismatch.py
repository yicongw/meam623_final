#!/usr/bin/env python3
"""Proposal-aligned dynamics-mismatch sweep.

Mirrors what the project proposal (Section IV-c, V) actually said:

  * The SIMULATOR (PyBullet) uses perturbed link masses at 5%, 10%, 20%
    of the nominal value; the controller continues to use the nominal
    inertia model.
  * For each perturbation level we compare two controller settings:
      (i)  baseline VPP-TC (no ε-margin on the viability bounds)
      (ii) VPP-TC with an ε-margin on the viability bounds

For each (pct, eps, seed) cell we collect:
  - whether the run self-collided
  - worst joint-position / joint-velocity overshoot
  - min self-collision distance
  - min Gamma value
  - whether the EE reached the target

The sweep is designed to make the proposal's claim falsifiable: if the
ε-margin helps, the (eps>0) column should have fewer collisions / smaller
joint-limit overshoot than the (eps=0) column at the SAME perturbation level.

Output:
    output/proposal_mismatch.csv
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import List

import numpy as np
import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcts", type=float, nargs="+",
                    default=[0.0, 5.0, 10.0, 15.0],
                    help="Link-mass perturbation percentages to sweep.")
    ap.add_argument("--epsilons", type=float, nargs="+",
                    default=[0.0, 0.10],
                    help="ε-margin values to sweep (fraction of |qdd_max|).")
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[11, 22, 33],
                    help="Mass-perturbation seeds.  Same seed -> same per-link "
                         "perturbation pattern, so we can pair (eps=0, eps>0) "
                         "runs apples-to-apples.")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--stepsize", type=float, default=2e-3)
    ap.add_argument("--target", type=float, nargs=3,
                    default=[0.0, -0.6, 0.3],
                    help="EE target.  Default = the original VPP-TC scenario "
                         "(target near base + sinusoidal obstacle).")
    ap.add_argument("--gain", type=float, default=50.0)
    ap.add_argument("--out", type=str,
                    default=os.path.join(_OUTPUT_DIR, "proposal_mismatch.csv"))
    return ap.parse_args()


def run_one(pct, eps, seed, args) -> dict:
    eps_tag = f"e{int(eps*100):02d}"
    tag = f"pm_p{int(pct):02d}_{eps_tag}_s{seed:02d}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--duration", str(args.duration),
        "--stepsize", str(args.stepsize),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(seed),
        "--epsilon-margin", str(eps),
        "--planner-gain", str(args.gain),
        "--target-pos", *map(str, args.target),
        "--tag", tag,
    ]
    last_err = None
    for attempt in range(3):
        res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                             capture_output=True, text=True)
        if res.returncode == 0:
            break
        last_err = res.stderr[-1500:]
        if "torch_cuda.dll" in last_err or "WinError 193" in last_err:
            time.sleep(2.0 * (attempt + 1))
            continue
        break
    if res.returncode != 0:
        print(f"\n!!! FAILED rc={res.returncode}  tag={tag}")
        print("STDERR[-1500:]\n" + (last_err or ""))
        raise RuntimeError(tag)

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return {
        "pct": pct, "eps": eps, "seed": seed,
        "self_collided": bool((df["self_collision_dist"] < 0).any()),
        "min_self_dist": float(df["self_collision_dist"].min()),
        "min_gamma":     float(df["gamma"].min()),
        "max_q_violation":  float(df["q_lim_violation"].max()),
        "max_qd_violation": float(df["qd_lim_violation"].max()),
        "max_qd_abs":       float(df["qd_max_abs"].max()),
        "soft_pct":  float(df["soft_fallback"].mean()) * 100.0,
        "final_target_dist": float(df["target_dist"].iloc[-1]),
        "csv":       os.path.basename(csv_path),
    }


def main():
    args = get_args()
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    rows: List[dict] = []
    n_total = len(args.pcts) * len(args.epsilons) * len(args.seeds)
    n_done = 0

    for pct in args.pcts:
        for eps in args.epsilons:
            for seed in args.seeds:
                t0 = time.time()
                row = run_one(pct, eps, seed, args)
                dt = time.time() - t0
                n_done += 1
                print(f"[{n_done:3d}/{n_total}]  pct={pct:>5.1f}%  "
                      f"eps={eps:.2f}  seed={seed:>2d}  "
                      f"sc_min={row['min_self_dist']*100:6.2f}cm  "
                      f"\u0393_min={row['min_gamma']:5.2f}  "
                      f"q_over={row['max_q_violation']*1000:5.2f}mm  "
                      f"qd_over={row['max_qd_violation']:5.3f}  "
                      f"final={row['final_target_dist']*1000:5.1f}mm  "
                      f"coll={row['self_collided']}  ({dt:.1f}s)")
                rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"\n[sweep] saved -> {args.out}")

    # ---------------- Summary ----------------
    print("\n=== Summary: collisions per (pct, eps) cell ===")
    pivot_coll = df.pivot_table(
        index="pct", columns="eps",
        values="self_collided", aggfunc="sum"
    )
    print(pivot_coll.to_string())

    print("\n=== Mean min_self_dist (cm) per (pct, eps) cell ===")
    pivot_sc = df.pivot_table(
        index="pct", columns="eps",
        values="min_self_dist", aggfunc="mean"
    ) * 100.0
    print(pivot_sc.round(3).to_string())

    print("\n=== Mean max_qd_abs (rad/s) per (pct, eps) cell ===")
    pivot_qd = df.pivot_table(
        index="pct", columns="eps",
        values="max_qd_abs", aggfunc="mean"
    )
    print(pivot_qd.round(3).to_string())

    print("\n=== Mean final_target_dist (mm) per (pct, eps) cell ===")
    pivot_fin = df.pivot_table(
        index="pct", columns="eps",
        values="final_target_dist", aggfunc="mean"
    ) * 1000.0
    print(pivot_fin.round(2).to_string())


if __name__ == "__main__":
    main()
