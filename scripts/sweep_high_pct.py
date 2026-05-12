#!/usr/bin/env python3
"""High-perturbation sweep: when does VPP-TC actually self-collide?

Pushes link-mass perturbation up to 50% on the same obstacle scenario
that proposal_mismatch.csv used, with ε=0 only. We want to know:

  At what perturbation level does self_collided flip from False to True?
  Or does the passive-damping fallback always save it?

Also tries one aggressive no-obstacle scenario (low_reach) which is the
only one that actually drove qd to saturation in the previous explore.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

# (label, target, gain, no_obstacles)
SCENARIOS = [
    ("obs",       [0.00, -0.60, 0.30],  50, False),  # proposal scenario
    ("low_reach", [0.45, -0.20, 0.10], 400, True),   # the one that broke before
]
PCTS  = [15.0, 20.0, 25.0, 30.0, 40.0, 50.0]
SEEDS = [11, 22, 33]
DURATION = 5.0


def run_one(label, target, gain, no_obs, pct, seed):
    tag = f"hp_{label}_p{int(pct):02d}_s{seed:02d}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-reactive",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(seed),
        "--epsilon-margin", "0.0",
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if no_obs:
        cmd.append("--no-obstacles")
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
        "label": label, "pct": pct, "seed": seed,
        "self_collided": bool((df["self_collision_dist"] < 0).any()),
        "min_self_dist":   float(df["self_collision_dist"].min()),
        "min_gamma":       float(df["gamma"].min()),
        "max_q_violation": float(df["q_lim_violation"].max()),
        "max_qd_abs":      float(df["qd_max_abs"].max()),
        "soft_pct":        float(df["soft_fallback"].mean()) * 100.0,
        "final_dist":      float(df["target_dist"].iloc[-1]),
    }


def main():
    rows = []
    n_total = len(SCENARIOS) * len(PCTS) * len(SEEDS)
    n_done = 0
    for label, target, gain, no_obs in SCENARIOS:
        for pct in PCTS:
            for seed in SEEDS:
                t0 = time.time()
                row = run_one(label, target, gain, no_obs, pct, seed)
                dt = time.time() - t0
                n_done += 1
                marker = " ***COLL***" if row["self_collided"] else ""
                print(f"[{n_done:2d}/{n_total}] {label:10s} "
                      f"pct={pct:>4.1f}% seed={seed:>2d}  "
                      f"sc={row['min_self_dist']*100:6.2f}cm  "
                      f"\u0393={row['min_gamma']:7.2f}  "
                      f"q_over={row['max_q_violation']*1000:6.2f}mm  "
                      f"qd_max={row['max_qd_abs']:6.2f}  "
                      f"soft={row['soft_pct']:5.1f}%  "
                      f"final={row['final_dist']*1000:6.1f}mm"
                      f"{marker}  ({dt:.1f}s)")
                rows.append(row)

    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "high_pct.csv")
    df.to_csv(out, index=False)
    print(f"\n[hp] saved -> {out}")

    # Per-scenario collision rate vs pct
    print("\n=== Collision rate (out of 3 seeds) per (scenario, pct) ===")
    pivot = df.pivot_table(index="pct", columns="label",
                           values="self_collided", aggfunc="sum")
    print(pivot.to_string())

    print("\n=== Mean min_self_dist (cm) per (scenario, pct) ===")
    pivot2 = df.pivot_table(index="pct", columns="label",
                            values="min_self_dist", aggfunc="mean") * 100
    print(pivot2.round(2).to_string())

    print("\n=== Mean qd_max (rad/s) per (scenario, pct) ===")
    pivot3 = df.pivot_table(index="pct", columns="label",
                            values="max_qd_abs", aggfunc="mean")
    print(pivot3.round(2).to_string())


if __name__ == "__main__":
    main()
