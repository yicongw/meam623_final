#!/usr/bin/env python3
"""For each candidate aggressive scenario, run VPP-TC vs CFC head-to-head.

A 'CFC' run is `simulate.py --no-viability --no-gamma`.
We tabulate side-by-side metrics so we can pick a scenario in which the two
controllers visibly diverge (e.g., CFC violates while VPP-TC doesn't).
"""

import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

QD_LIM = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])

CANDIDATES = [
    # (label, target, gain, duration)
    ("under_arm",   [0.10, -0.10, 0.20], 300, 5.0),
    ("near_base",   [0.10,  0.10, 0.30], 200, 5.0),
    ("under_arm_hi",[0.10, -0.10, 0.20], 500, 5.0),
    ("base_top",    [0.05,  0.05, 0.20], 400, 5.0),
    ("snake",       [0.30,  0.20, 0.15], 400, 5.0),
]


def run(label, target, gain, duration, mode):
    tag = f"cmp_{label}_{mode}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-obstacles",
        "--no-reactive",
        "--duration", str(duration),
        "--planner-gain", str(gain),
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if mode == "cfc":
        cmd += ["--no-viability", "--no-gamma"]
    res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                         capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-1500:])
        raise RuntimeError(f"{label}/{mode} failed")

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return df, csv_path


def summarise(df, label, mode):
    return {
        "label":  label,
        "mode":   mode,
        "gamma_min":   float(df["gamma"].min()),
        "gamma_pct":   float(df["gamma_active"].mean()) * 100,
        "sc_min":      float(df["self_collision_dist"].min()),
        "qd_max":      float(df["qd_max_abs"].max()),
        "qd_over_max": float(df["qd_lim_violation"].max()),
        "q_over_max":  float(df["q_lim_violation"].max()),
        "self_coll":   bool((df["self_collision_dist"] < 0).any()),
        "final_d":     float(df["target_dist"].iloc[-1]),
        "max_S":       float(df["storage"].max()),
    }


def main():
    rows = []
    for label, target, gain, dur in CANDIDATES:
        for mode in ("vpptc", "cfc"):
            t0 = time.time()
            df, _ = run(label, target, gain, dur, mode)
            print(f"  {label:14s} {mode:5s} ran in {time.time()-t0:.1f}s")
            rows.append(summarise(df, label, mode))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(_OUTPUT_DIR, "compare_summary.csv"), index=False)
    print()
    cols = ["label", "mode", "gamma_min", "gamma_pct", "sc_min",
            "qd_max", "qd_over_max", "q_over_max",
            "self_coll", "final_d", "max_S"]
    print(out[cols].to_string(index=False))


if __name__ == "__main__":
    main()
