#!/usr/bin/env python3
"""Sweep the QP's inertia estimate vs the true PyBullet model.

For each mass-scale alpha in ALPHAS, runs simulate.py twice:
  * controller = "VPP-TC"   (viability ON, Gamma ON)
  * controller = "CFC-base" (viability OFF, Gamma OFF)

The QP sees  M_qp = alpha * M_true,  tau_id_qp = alpha * tau_id_true
while PyBullet integrates the true (unscaled) dynamics.

Each run lands its own CSV under output/.  We then condense every CSV into
one summary row and write all rows to output/sweep_mismatch.csv.

Usage
-----
    python scripts/sweep_mismatch.py
    python scripts/sweep_mismatch.py --duration 5 --alphas 0.7 1.0 1.3
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

# Default 7-point sweep: from -50% to +50% inertia mismatch.
ALPHAS_DEFAULT = [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5]


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alphas", type=float, nargs="+", default=ALPHAS_DEFAULT,
                    help="QP mass-scale values to sweep")
    ap.add_argument("--duration", type=float, default=6.0,
                    help="Per-run sim duration [s]")
    ap.add_argument("--stepsize", type=float, default=2e-3)
    ap.add_argument("--seed", type=int, default=28)
    ap.add_argument("--out-csv", type=str,
                    default=os.path.join(_OUTPUT_DIR, "sweep_mismatch.csv"))
    ap.add_argument("--scenario-tag", type=str, default="mm",
                    help="Tag prefix for the run CSVs (e.g. 'mm' or 'aggr').")
    ap.add_argument("--target-pos", type=float, nargs=3, default=None,
                    help="Override target [x y z]")
    ap.add_argument("--planner-gain", type=float, default=None)
    ap.add_argument("--no-obstacles", action="store_true")
    ap.add_argument("--no-reactive", action="store_true")
    return ap.parse_args()


def run_one(alpha: float, mode: str, args) -> str:
    """Run simulate.py once and return the path to the produced CSV."""
    tag = f"{args.scenario_tag}_a{alpha:0.2f}_{mode}".replace(".", "p")
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--duration", str(args.duration),
        "--stepsize", str(args.stepsize),
        "--seed",     str(args.seed),
        "--qp-mass-scale", str(alpha),
        "--tag", tag,
    ]
    if args.target_pos is not None:
        cmd += ["--target-pos", *map(str, args.target_pos)]
    if args.planner_gain is not None:
        cmd += ["--planner-gain", str(args.planner_gain)]
    if args.no_obstacles:
        cmd += ["--no-obstacles"]
    if args.no_reactive:
        cmd += ["--no-reactive"]
    if mode == "cfc":
        cmd += ["--no-viability", "--no-gamma"]
    elif mode == "vpptc":
        pass  # default flags
    else:
        raise ValueError(mode)

    print(f"\n[run] alpha={alpha:.2f}  mode={mode}")
    print(f"      cmd: {' '.join(cmd)}")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                         capture_output=True, text=True)
    dt = time.time() - t0
    if res.returncode != 0:
        print(res.stdout[-2000:])
        print(res.stderr[-2000:])
        raise RuntimeError(f"simulate.py failed for alpha={alpha} mode={mode}")

    # Locate the CSV that was just produced (by tag).
    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    if not csvs:
        raise FileNotFoundError(f"no CSV with tag {tag} in {_OUTPUT_DIR}")
    # Pick the freshest one in case of a previous run with the same tag.
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    print(f"      done in {dt:.1f}s  ->  {os.path.basename(csv_path)}")
    return csv_path


def summarise(csv_path: str, alpha: float, mode: str) -> dict:
    df = pd.read_csv(csv_path)
    # Self-collision = closest-point distance going negative anywhere.
    self_collided = bool((df["self_collision_dist"] < 0).any())
    # External-obstacle hit = closest center-distance falling below the
    # 5cm sphere radius (the obstacle radius used in simulate.py).
    obs_hit = bool((df["real_dist"] < 0.05).any())

    summary = {
        "alpha":             alpha,
        "mode":              mode,
        "ran_full_duration": (df["time"].iloc[-1] >= df["time"].iloc[-2]),
        "duration_reached":  float(df["time"].iloc[-1]),
        "min_self_dist":     float(df["self_collision_dist"].min()),
        "min_real_dist":     float(df["real_dist"].min()),
        "min_pred_dist":     float(df["pred_dist"].min()),
        "min_gamma":         float(df["gamma"].min()),
        "max_storage":       float(df["storage"].max()),
        "final_target_dist": float(df["target_dist"].iloc[-1]),
        "min_target_dist":   float(df["target_dist"].min()),
        "self_collided":     self_collided,
        "obstacle_hit":      obs_hit,
        "csv":               os.path.basename(csv_path),
    }
    return summary


def main():
    args = get_args()
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    rows: List[dict] = []
    for alpha in args.alphas:
        for mode in ("vpptc", "cfc"):
            csv_path = run_one(alpha, mode, args)
            row = summarise(csv_path, alpha, mode)
            print(f"      {mode:6s} | min_real_dist={row['min_real_dist']:.3f}  "
                  f"min_gamma={row['min_gamma']:.2f}  "
                  f"max_S={row['max_storage']:.1f}  "
                  f"final_d={row['final_target_dist']:.3f}  "
                  f"self_coll={row['self_collided']}  obs_hit={row['obstacle_hit']}")
            rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(args.out_csv, index=False)
    print(f"\n[sweep] saved -> {args.out_csv}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
